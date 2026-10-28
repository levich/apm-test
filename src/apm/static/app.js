"use strict";
const ctx = JSON.parse(document.getElementById("apm-context").textContent),
  t = ctx.t,
  page = ctx.page;
const csrf = document.querySelector('meta[name="csrf-token"]').content,
  content = document.getElementById("content");
const dialog = document.getElementById("editor"),
  fields = document.getElementById("editor-fields");
let editorSubmit = null;
let editorReveal = null;
let fieldNumber = 0;
let activeFieldHelp = null;
function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== undefined) node.setAttribute(key, value);
  }
  for (const child of children) if (child) node.append(child);
  return node;
}
function text(value) {
  return document.createTextNode(value ?? "");
}
function message(value, error = false) {
  const box = document.getElementById("notice");
  box.className = `alert ${error ? "alert-danger" : "alert-info"}`;
  box.textContent = value;
}
async function api(path, options = {}) {
  const headers = { "X-CSRF-Token": csrf, ...options.headers };
  if (options.body && !(options.body instanceof FormData))
    headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  const result = await response.json();
  if (response.status === 401) {
    location.assign("/login");
    throw new Error("Authentication required");
  }
  if (!response.ok)
    throw new Error(
      typeof result.detail === "string"
        ? result.detail
        : JSON.stringify(result.detail),
    );
  return result;
}
function badge(value) {
  const success = ["succeeded", "applied", "ready", "manual", "up", "valid"].includes(value);
  return el("span", {
    class: `badge ${success ? "bg-green-lt" : ["failed", "error", "rollback_failed", "down", "expired", "key_mismatch", "invalid_files", "domain_mismatch", "not_yet_valid"].includes(value) ? "bg-red-lt" : ["partial", "expiring", "pending", "running", "awaiting_confirmation"].includes(value) ? "bg-yellow-lt" : "bg-secondary-lt"}`,
    text: t[`state_${value}`] || t[value] || value,
  });
}
function card(title, body) {
  return el("section", { class: "card mb-4" }, [
    el("div", { class: "card-header" }, [
      el("h2", { class: "card-title", text: title }),
    ]),
    el("div", { class: "card-body" }, [body]),
  ]);
}
function button(label, action, primary = false) {
  return el("button", {
    type: "button",
    class: `btn btn-sm ${primary ? "btn-primary" : "btn-outline-secondary"}`,
    text: label,
    onclick: async () => {
      try {
        await action();
      } catch (error) {
        message(error.message, true);
      }
    },
  });
}
function table(headers, rows) {
  const head = el("thead", {}, [
      el(
        "tr",
        {},
        headers.map((h) => el("th", { text: h })),
      ),
    ]),
    body = el("tbody");
  for (const row of rows)
    body.append(
      el(
        "tr",
        {},
        row.map((value) =>
          el("td", {}, [typeof value === "object" ? value : text(value)]),
        ),
      ),
    );
  if (!rows.length)
    body.append(
      el("tr", {}, [
        el("td", {
          colspan: headers.length,
          class: "empty-state",
          text: t.empty,
        }),
      ]),
    );
  return el("div", { class: "card" }, [
    el("div", { class: "table-responsive" }, [
      el("table", { class: "table table-vcenter card-table" }, [head, body]),
    ]),
  ]);
}
const labels = {
  force_ssl: "HTTP → HTTPS",
  http2: "HTTP/2",
  http3: "HTTP/3",
  dns_profile_id: t["dns-profiles"],
  certificate_id: t.certificates,
  access_ids: t["access-lists"],
  upstream_id: t.upstreams,
  auth_provider_id: t["auth-providers"],
  authentik_mode: t.authentik_mode,
  header_policy_id: t["header-policies"],
  tls_policy_id: t["tls-policies"],
  client_ca_id: t["client-cas"],
  geo_policy_id: t["geo-policies"],
  crowdsec_profile_id: t["crowdsec-profiles"],
  listen_port: ctx.language === "ru" ? "Входящий порт" : "Listening port",
  acme_terms_agreed:
    ctx.language === "ru"
      ? "Принимаю условия выбранного ACME CA"
      : "I agree to the selected ACME CA terms",
  acme_email: t.email,
};
const references = {
  certificate_id: "certificates",
  dns_profile_id: "dns-profiles",
  upstream_id: "upstreams",
  access_ids: "access-lists",
  auth_provider_id: "auth-providers",
  header_policy_id: "header-policies",
  tls_policy_id: "tls-policies",
  client_ca_id: "client-cas",
  geo_policy_id: "geo-policies",
  crowdsec_profile_id: "crowdsec-profiles",
  ech_id: "ech",
};
const managedFields = new Set([
  "fingerprint",
  "expires_at",
  "status",
  "config",
  "current_key",
  "previous_key",
  "pending_key",
  "database_version",
]);
function labelFor(key, schema) {
  return t[key] || labels[key] || schema.title || key.replaceAll("_", " ");
}
function closeFieldHelp(restoreFocus = false) {
  if (!activeFieldHelp) return;
  const { popup, trigger, native } = activeFieldHelp;
  activeFieldHelp = null;
  if (native && popup.matches(":popover-open")) popup.hidePopover();
  else if (!native) popup.hidden = true;
  trigger.setAttribute("aria-expanded", "false");
  if (restoreFocus && trigger.isConnected) trigger.focus({ preventScroll: true });
}
function positionFieldHelp() {
  if (!activeFieldHelp) return;
  const { popup, trigger } = activeFieldHelp,
    anchor = trigger.getBoundingClientRect(),
    body = dialog.querySelector(".dialog-body").getBoundingClientRect();
  if (anchor.bottom < body.top || anchor.top > body.bottom) {
    closeFieldHelp();
    return;
  }
  const size = popup.getBoundingClientRect();
  const left = Math.max(16, Math.min(anchor.left + anchor.width / 2 - size.width / 2,
    window.innerWidth - size.width - 16));
  const below = anchor.bottom + 8;
  const top = below + size.height <= window.innerHeight - 16 ? below
    : Math.max(16, anchor.top - size.height - 8);
  popup.style.left = `${left}px`;
  popup.style.top = `${top}px`;
}
function setFieldLabel(wrapper, label) {
  wrapper.querySelector("label").textContent = label;
  const trigger = wrapper.querySelector(".field-help-button");
  if (trigger) {
    trigger.setAttribute("aria-label", `${t.help}: ${label}`);
    trigger.title = `${t.help}: ${label}`;
    wrapper.querySelector(".field-help-title").textContent = label;
  }
}
function addFieldHelp(wrapper, key, description = null) {
  const explanation = t.field_help_pages?.[page]?.[key] || t.field_help?.[key] || description;
  if (!explanation) return;
  const label = wrapper.querySelector(":scope > label");
  if (!label) return;
  const title = label.textContent.replace(/\s\*$/, ""),
    id = `field-help-${++fieldNumber}`,
    popup = el("div", {
      id, class: "field-help-popup", popover: "auto", role: "note",
      "aria-labelledby": `${id}-title`,
    }),
    trigger = el("button", {
      type: "button", class: "field-help-button", text: "?",
      "aria-label": `${t.help}: ${title}`, "aria-expanded": "false",
      "aria-controls": id, title: `${t.help}: ${title}`,
    }),
    native = typeof popup.showPopover === "function";
  if (!native) {
    popup.removeAttribute("popover");
    popup.hidden = true;
  }
  popup.append(
    el("div", { class: "field-help-head" }, [
      el("strong", { id: `${id}-title`, class: "field-help-title", text: title }),
      el("button", { type: "button", class: "field-help-close", text: "×",
        "aria-label": t.close_help, onclick: () => closeFieldHelp(true) }),
    ]),
    el("p", { id: `${id}-description`, text: explanation }),
    el("a", { href: `/ui/documentation/${page}#${page === "access-lists" && ["action", "address"].includes(key) ? `rules-${key}` : key}`, target: "_blank",
      rel: "noopener", text: t.read_documentation }),
  );
  wrapper.classList.add("has-field-help");
  wrapper.prepend(trigger);
  wrapper.append(popup);
  const control = wrapper.querySelector(":scope > input,:scope > select,:scope > textarea,:scope > label > input");
  if (control) {
    if (label.htmlFor && !control.id) control.id = label.htmlFor;
    control.setAttribute("aria-describedby", `${id}-description`);
  }
  trigger.addEventListener("click", () => {
    if (activeFieldHelp?.popup === popup) {
      closeFieldHelp();
      return;
    }
    closeFieldHelp();
    activeFieldHelp = { popup, trigger, native };
    if (native) popup.showPopover();
    else popup.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    positionFieldHelp();
  });
  popup.addEventListener("toggle", (event) => {
    if (event.newState === "closed") {
      trigger.setAttribute("aria-expanded", "false");
      if (activeFieldHelp?.popup === popup) activeFieldHelp = null;
    }
  });
}
function makeField(key, raw, value, definitions, pools, required = false) {
  const node = buildField(key, raw, value, definitions, pools, required);
  addFieldHelp(node.element, key, raw.description);
  return node;
}
function buildField(key, raw, value, definitions, pools, required = false) {
  let schema = raw;
  if (schema.$ref) schema = definitions[schema.$ref.split("/").pop()];
  if (schema.anyOf)
    schema = schema.anyOf.find((s) => s.type !== "null") || schema;
  if (schema.$ref) schema = definitions[schema.$ref.split("/").pop()];
  if (value === undefined && schema.default !== undefined)
    value = structuredClone(schema.default);
  const wrapper = el("div", { class: "schema-field", "data-field": key });
  const label = labelFor(key, schema);
  const fieldId = `field-${++fieldNumber}`;
  wrapper.append(
    el("label", { class: "form-label", for: fieldId, text: label + (required ? " *" : "") }),
  );
  if (key === "access_ids") {
    const ids = [...(value || [])],
      list = el("div", { class: "mb-2" }),
      select = el("select", { class: "form-select mb-2" }, [
        el("option", { value: "", text: "—" }),
        ...(pools["access-lists"] || []).map((r) =>
          el("option", { value: r.id, text: r.name }),
        ),
      ]);
    function render() {
      list.replaceChildren();
      ids.forEach((id, index) => {
        const name =
          (pools["access-lists"] || []).find((r) => r.id === id)?.name || id;
        list.append(
          el("div", { class: "d-flex gap-2 align-items-center mb-2" }, [
            text(`${index + 1}. ${name}`),
            button("↑", () => {
              if (index) {
                [ids[index - 1], ids[index]] = [ids[index], ids[index - 1]];
                render();
              }
            }),
            button("↓", () => {
              if (index < ids.length - 1) {
                [ids[index + 1], ids[index]] = [ids[index], ids[index + 1]];
                render();
              }
            }),
            button("×", () => {
              ids.splice(index, 1);
              render();
            }),
          ]),
        );
      });
    }
    wrapper.append(
      el("small", {
        class: "text-secondary d-block mb-2",
        text:
          ctx.language === "ru"
            ? "Проверка сверху вниз. Satisfy и передача авторизации берутся из первого списка."
            : "Evaluated in order. Satisfy and authorization forwarding come from the first list.",
      }),
      list,
      select,
      button(t.create, () => {
        if (select.value && !ids.includes(select.value)) {
          ids.push(select.value);
          render();
        }
      }),
    );
    render();
    return { element: wrapper, get: () => ids };
  }
  if (references[key]) {
    const select = el("select", { class: "form-select", id: fieldId });
    if (schema.type === "array") select.multiple = true;
    else select.append(el("option", { value: "", text: "—" }));
    for (const resource of pools[references[key]] || []) {
      const option = el("option", { value: resource.id, text: resource.name });
      option.selected = Array.isArray(value)
        ? value.includes(resource.id)
        : value === resource.id;
      select.append(option);
    }
    wrapper.append(select);
    return {
      element: wrapper,
      get: () =>
        select.multiple
          ? [...select.selectedOptions].map((o) => o.value)
          : select.value || null,
    };
  }
  if (schema.enum) {
    const select = el("select", { class: "form-select", id: fieldId });
    for (const item of schema.enum) {
      const option = el("option", { value: String(item),
        text: key === "authentik_mode" ? t[`authentik_mode_${item}`] : String(item) });
      option.selected = item === value;
      select.append(option);
    }
    wrapper.append(select);
    return {
      element: wrapper,
      get: () =>
        schema.type === "integer" ? Number(select.value) : select.value,
    };
  }
  if (schema.type === "boolean") {
    const input = el("input", { type: "checkbox", class: "form-check-input", id: fieldId });
    wrapper.classList.add("schema-switch");
    input.checked = !!value;
    wrapper.append(input);
    return { element: wrapper, get: () => input.checked };
  }
  if (schema.type === "object") {
    if (schema.properties) {
      const nodes = {};
      const group = el("div", { class: "schema-group" });
      for (const [child, spec] of Object.entries(schema.properties)) {
        nodes[child] = makeField(
          child,
          spec,
          value?.[child],
          definitions,
          pools,
          (schema.required || []).includes(child),
        );
        group.append(nodes[child].element);
      }
      wrapper.append(group);
      return {
        element: wrapper,
        get: () =>
          Object.fromEntries(
            Object.entries(nodes).map(([k, v]) => [k, v.get()]),
          ),
      };
    }
    const input = el("textarea", {
      class: "form-control",
      rows: 4,
      placeholder: "Header-Name=value",
    });
    input.value = Object.entries(value || {})
      .map(([k, v]) => `${k}=${v}`)
      .join("\n");
    wrapper.append(input);
    return {
      element: wrapper,
      get: () =>
        Object.fromEntries(
          input.value
            .split("\n")
            .filter((v) => v.trim())
            .map((line) => {
              const n = line.indexOf("=");
              if (n < 1) throw new Error(`${label}: key=value`);
              return [line.slice(0, n).trim(), line.slice(n + 1)];
            }),
        ),
    };
  }
  if (schema.type === "array") {
    let item = schema.items || {};
    if (item.$ref) item = definitions[item.$ref.split("/").pop()];
    if (item.type === "object") {
      const list = el("div", { class: "array-items" }),
        nodes = [];
      const add = (value) => {
        const node = makeField("", item, value, definitions, pools);
        node.element.classList.add("schema-array-item");
        node.element.prepend(
          button("×", () => {
            node.element.remove();
            nodes.splice(nodes.indexOf(node), 1);
          }),
        );
        nodes.push(node);
        list.append(node.element);
      };
      (value || []).forEach(add);
      wrapper.append(
        list,
        button("＋", () => add({})),
      );
      return { element: wrapper, get: () => nodes.map((n) => n.get()) };
    }
    const input = el("textarea", { class: "form-control", rows: 3, id: fieldId });
    input.value = (value || []).join("\n");
    wrapper.append(input);
    return {
      element: wrapper,
      get: () =>
        input.value
          .split(/\n|,/)
          .map((v) => v.trim())
          .filter(Boolean)
          .map((v) => (item.type === "integer" ? Number(v) : v)),
    };
  }
  const multiline =
    key.includes("snippet") || key === "advanced" || key === "default_html";
  const input = multiline
    ? el("textarea", { class: "form-control", rows: 5 })
    : el("input", {
        class: "form-control",
        type: ["integer", "number"].includes(schema.type) ? "number" : "text",
      });
  input.value = value ?? "";
  input.id = fieldId;
  if (schema.minimum !== undefined) input.min = schema.minimum;
  if (schema.maximum !== undefined) input.max = schema.maximum;
  if (required) input.required = true;
  wrapper.append(input);
  return {
    element: wrapper,
    get: () =>
      ["integer", "number"].includes(schema.type)
        ? Number(input.value)
        : input.value === "" && !required && raw.anyOf
          ? null
          : input.value,
  };
}
function proxySSL(nodes, pools, resource) {
  const current = resource?.data || {},
    selector = nodes.certificate_id.element.querySelector("select"),
    method = nodes.tls.element.querySelector("select"),
    email = nodes.acme_email.element.querySelector("input"),
    terms = nodes.acme_terms_agreed.element.querySelector("input"),
    dns = nodes.dns_profile_id.element.querySelector("select"),
    readDNS = nodes.dns_profile_id.get,
    requestLabel = ctx.letsencrypt ? t.ssl_request_letsencrypt : t.ssl_request;
  setFieldLabel(nodes.certificate_id.element, t.ssl_certificate);
  selector.replaceChildren(
    el("option", { value: "", text: t.ssl_none }),
    el("option", { value: "new", text: requestLabel }),
  );
  for (const certificate of pools.certificates || []) {
    if (!certificate.enabled && certificate.id !== current.certificate_id) continue;
    selector.append(el("option", {
      value: certificate.id,
      text: `${certificate.name} · ${t[`certificate_${certificate.data.status}`] || certificate.data.status}`,
    }));
  }
  if (current.certificate_id && ![...selector.options].some((o) => o.value === current.certificate_id))
    selector.append(el("option", { value: current.certificate_id, text: current.certificate_id }));
  selector.value = current.tls && current.tls !== "off"
    ? current.certificate_id || "new" : "";
  setFieldLabel(nodes.tls.element, t.ssl_method);
  method.replaceChildren(
    el("option", { value: "http", text: t.ssl_http }),
    el("option", { value: "dns", text: t.ssl_dns }),
  );
  method.value = current.tls === "dns" ? "dns" : "http";
  email.type = "email";
  email.autocomplete = "email";
  email.value = current.acme_email || ctx.email || "";
  setFieldLabel(nodes.acme_terms_agreed.element, t.ssl_terms);
  nodes.acme_terms_agreed.element.prepend(terms);
  if (ctx.letsencrypt) nodes.acme_terms_agreed.element.append(el("a", {
    href: "https://letsencrypt.org/repository/", target: "_blank", rel: "noopener noreferrer",
    class: "ssl-terms-link", text: t.ssl_terms_link,
  }));
  const hint = el("p", { class: "text-secondary ssl-hint" }),
    linkedHint = el("p", { class: "text-secondary ssl-hint", text: t.ssl_existing_hint }),
    progress = el("div", { class: "alert alert-info ssl-request-info", text: t.ssl_request_hint }),
    missingDNS = el("p", { class: "text-secondary", text: t.ssl_no_dns });
  nodes.tls.element.append(hint);
  nodes.certificate_id.element.append(linkedHint);
  nodes.dns_profile_id.element.append(missingDNS);
  nodes.tls.get = () => selector.value === "new" ? method.value
    : !selector.value ? "off"
    : selector.value === current.certificate_id && current.tls !== "off" ? current.tls : "certificate";
  nodes.certificate_id.get = () => selector.value && selector.value !== "new" ? selector.value : null;
  nodes.dns_profile_id.get = () => selector.value === "new" && method.value === "dns" ? readDNS()
    : selector.value === current.certificate_id && current.tls === "dns" ? current.dns_profile_id : null;
  nodes.acme_email.get = () => selector.value === "new" ? email.value : current.acme_email || "";
  nodes.acme_terms_agreed.get = () => selector.value === "new" ? terms.checked : current.acme_terms_agreed || false;
  function sync() {
    const request = selector.value === "new", enabled = !!selector.value,
      useDNS = request && method.value === "dns";
    for (const key of ["tls", "acme_email", "acme_terms_agreed"])
      nodes[key].element.hidden = !request;
    nodes.dns_profile_id.element.hidden = !useDNS;
    email.required = terms.required = request;
    email.disabled = terms.disabled = method.disabled = !request;
    dns.required = useDNS;
    dns.disabled = !useDNS;
    method.setCustomValidity(request && method.value === "http" && nodes.domains.get().some((d) => d.startsWith("*."))
      ? t.ssl_wildcard_dns : "");
    hint.textContent = useDNS ? t.ssl_dns_hint : t.ssl_http_hint;
    missingDNS.hidden = (pools["dns-profiles"] || []).some((r) => r.enabled);
    progress.hidden = !request;
    linkedHint.hidden = !enabled || request;
    for (const key of ["force_ssl", "http2", "http3", "tls_policy_id", "client_ca_id"])
      if (nodes[key]) nodes[key].element.hidden = !enabled;
    document.getElementById("editor-save").textContent = request ? t.save_request_certificate : t.save;
  }
  selector.addEventListener("change", () => {
    if (selector.value === "new" && nodes.domains.get().some((d) => d.startsWith("*."))) method.value = "dns";
    sync();
  });
  method.addEventListener("change", sync);
  nodes.domains.element.addEventListener("input", sync);
  sync();
  return { progress, sync, requested: () => selector.value === "new" };
}
function groupProxyFields(nodes, nameInput, enabledInput, pools, resource) {
  dialog.classList.add("proxy-editor");
  const tabs = el("div", { class: "proxy-tabs", role: "tablist", "aria-label": t.details }),
    panels = {}, buttons = {}, placed = new Set();
  function selectTab(key, focus = false) {
    closeFieldHelp();
    for (const name of Object.keys(panels)) {
      const active = name === key;
      panels[name].hidden = !active;
      buttons[name].setAttribute("aria-selected", String(active));
      buttons[name].tabIndex = active ? 0 : -1;
    }
    if (focus) buttons[key].focus();
  }
  for (const key of ["details", "locations", "ssl", "advanced"]) {
    panels[key] = el("div", { id: `proxy-panel-${key}`, class: "proxy-tab-panel", role: "tabpanel",
      "aria-labelledby": `proxy-tab-${key}`, hidden: "" });
    buttons[key] = el("button", { type: "button", id: `proxy-tab-${key}`, role: "tab",
      "aria-controls": panels[key].id, text: t[`proxy_${key}`], onclick: () => selectTab(key) });
    tabs.append(buttons[key]);
  }
  tabs.addEventListener("keydown", (event) => {
    const keys = Object.keys(buttons), index = keys.findIndex((key) => buttons[key] === event.target);
    if (index < 0 || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? keys.length - 1
      : (index + (event.key === "ArrowRight" ? 1 : -1) + keys.length) % keys.length;
    selectTab(keys[next], true);
  });
  fields.replaceChildren(tabs, ...Object.values(panels));
  const nameField = el("div", { class: "schema-field", "data-field": "name" }, [
    el("label", { for: nameInput.id, class: "form-label", text: t.name }), nameInput,
  ]);
  const enabledField = el("div", { class: "schema-field proxy-enabled", "data-field": "enabled" }, [
    el("label", { class: "proxy-enabled-label" }, [enabledInput, text(t.enabled)]),
  ]);
  addFieldHelp(nameField, "name");
  addFieldHelp(enabledField, "enabled");
  panels.details.append(el("div", { class: "proxy-identity" }, [nameField, enabledField]));
  function section(panel, title, keys, className = "") {
    const grid = el("div", { class: `proxy-grid ${className}` });
    for (const key of keys) if (nodes[key]) {
      placed.add(key);
      grid.append(nodes[key].element);
    }
    if (!grid.childElementCount) return;
    const block = el("section", { class: "proxy-section" });
    if (title) block.append(el("h3", { text: title }));
    block.append(grid);
    panels[panel].append(block);
    return block;
  }
  for (const key of ["domains", "locations", "certificate_id", "tls", "dns_profile_id", "acme_email", "acme_terms_agreed", "access_ids", "blocked_user_agents", "advanced"])
    if (nodes[key]) nodes[key].element.classList.add("proxy-full");
  nodes.domains.element.querySelector("textarea").required = true;
  section("details", "", ["domains"]);
  section("details", t.proxy_backend, ["scheme", "host", "port"], "proxy-backend");
  section("details", "", ["upstream_id", "access_ids"]);
  const upstreamTLS = section("details", t.proxy_upstream_tls, ["upstream_verify", "upstream_sni"]);
  upstreamTLS.append(el("p", { class: "text-secondary mt-3 mb-0", text: t.proxy_upstream_tls_hint }));
  function syncUpstreamTLS() {
    upstreamTLS.hidden = ![nodes.scheme.get(), ...nodes.locations.get().map((location) => location.scheme)]
      .some((scheme) => ["https", "grpcs"].includes(scheme));
  }
  nodes.scheme.element.addEventListener("change", syncUpstreamTLS);
  nodes.locations.element.addEventListener("change", syncUpstreamTLS);
  nodes.locations.element.addEventListener("click", syncUpstreamTLS);
  syncUpstreamTLS();
  section("details", t.proxy_options, ["websocket", "compression", "noindex"]);
  panels.details.append(button(t.ssl_configure, () => selectTab("ssl")));
  panels.locations.append(el("p", { class: "text-secondary", text: t.proxy_locations_hint }));
  section("locations", t.proxy_root_location, ["path", "strip_prefix", "access_mode"]);
  section("locations", t.proxy_locations, ["locations"]);
  section("ssl", "", ["certificate_id", "tls", "dns_profile_id", "acme_email", "acme_terms_agreed"]);
  const ssl = proxySSL(nodes, pools, resource);
  nodes.acme_terms_agreed.element.after(ssl.progress);
  section("ssl", t.proxy_options, ["force_ssl", "http2", "http3", "tls_policy_id", "client_ca_id"]);
  panels.advanced.append(el("p", { class: "text-secondary", text: t.proxy_advanced_hint }));
  section("advanced", t.proxy_access, ["auth_provider_id", "header_policy_id", "geo_policy_id", "crowdsec_profile_id", "blocked_user_agents"]);
  section("advanced", t.proxy_performance, ["rate", "connection_limit", "max_body_mb", "timeout_seconds", "request_buffering", "response_buffering", "upstream_compression"]);
  section("advanced", t.proxy_custom_config, ["advanced"]);
  section("advanced", "", Object.keys(nodes).filter((key) => !placed.has(key)));
  editorReveal = (input) => {
    const panel = input.closest(".proxy-tab-panel");
    if (panel) selectTab(Object.keys(panels).find((key) => panels[key] === panel));
  };
  selectTab("details");
  ssl.sync();
  return ssl;
}
function openEditor(title, onSubmit) {
  closeFieldHelp();
  editorReveal = null;
  dialog.classList.remove("proxy-editor");
  document.getElementById("editor-save").textContent = t.save;
  fields.replaceChildren();
  document.getElementById("editor-title").textContent = title;
  document.getElementById("editor-error").classList.add("d-none");
  editorSubmit = onSubmit;
  dialog.showModal();
}
async function editResource(resource = null) {
  const schema = await api(`/api/v1/schemas/${page}`),
    pools = {};
  await Promise.all(
    [...new Set(Object.values(references))].map(async (kind) => {
      pools[kind] = await api(`/api/v1/resources/${kind}`);
    }),
  );
  let nameInput,
    enabledInput,
    proxyEditor,
    nodes = {},
    credentialNodes = {};
  openEditor(`${resource ? t.edit : t.create} · ${t[page]}`, async () => {
    const data = Object.fromEntries(
      Object.entries(nodes).map(([key, node]) => [key, node.get()]),
    );
    for (const key of managedFields)
      if (resource && resource.data[key] !== undefined)
        data[key] = resource.data[key];
    if (ctx.role !== "admin" && resource)
      for (const key of [
        "advanced",
        "crowdsec_profile_id",
        "auth_provider_id",
        "tls_policy_id",
        "header_policy_id",
        "client_ca_id",
        "geo_policy_id",
      ])
        if (resource.data[key] !== undefined) data[key] = resource.data[key];
    const body = { name: nameInput.value, enabled: enabledInput.checked, data };
    const credentials = Object.fromEntries(
      Object.entries(credentialNodes)
        .map(([key, input]) => [key, input.value])
        .filter(([k, v]) => v),
    );
    if (Object.keys(credentials).length) body.credentials = credentials;
    if (page === "access-lists") {
      const raw = document.getElementById("basic-credentials")?.value.trim();
      if (raw)
        body.credentials = Object.fromEntries(
          raw.split("\n").map((line) => {
            const i = line.indexOf("=");
            if (i < 1) throw new Error("username=password");
            return [line.slice(0, i), line.slice(i + 1)];
          }),
        );
    }
    const url = `/api/v1/resources/${page}${resource ? "/" + resource.id : ""}`;
    await api(url, {
      method: resource ? "PUT" : "POST",
      body: JSON.stringify(body),
      headers: resource ? { "If-Match": String(resource.version) } : {},
    });
    dialog.close();
    message(proxyEditor?.requested() ? t.ssl_request_saved : t.operation_saved);
    await load();
  });
  nameInput = el("input", {
    id: "editor-name",
    class: "form-control mb-3",
    required: "",
    placeholder: t.name,
  });
  nameInput.value = resource?.name || "";
  enabledInput = el("input", {
    id: "editor-enabled",
    type: "checkbox",
    class: "form-check-input me-2",
  });
  enabledInput.checked = resource?.enabled ?? true;
  if (page === "sites") {
    nameInput.classList.remove("mb-3");
    const nameField = el("div", { class: "schema-field", "data-field": "name" }, [
      el("label", { class: "form-label", for: nameInput.id, text: t.name }), nameInput,
    ]);
    const enabledField = el("div", { class: "schema-field", "data-field": "enabled" }, [
      el("label", { class: "form-check", for: enabledInput.id }, [enabledInput, text(t.enabled)]),
    ]);
    addFieldHelp(nameField, "name");
    addFieldHelp(enabledField, "enabled");
    fields.append(nameField, enabledField);
  } else {
    fields.append(el("label", { class: "form-label", text: t.name }), nameInput);
    fields.append(el("label", { class: "form-check mb-4" }, [enabledInput, text(t.enabled)]));
  }
  for (const [key, spec] of Object.entries(schema.properties)) {
    if (managedFields.has(key)) continue;
    if (
      ctx.role !== "admin" &&
      [
        "advanced",
        "crowdsec_profile_id",
        "auth_provider_id",
        "tls_policy_id",
        "header_policy_id",
        "client_ca_id",
        "geo_policy_id",
      ].includes(key)
    )
      continue;
    nodes[key] = makeField(
      key,
      spec,
      resource?.data[key],
      schema.$defs || {},
      pools,
      (schema.required || []).includes(key),
    );
    fields.append(nodes[key].element);
  }
  if (page === "proxy-hosts") proxyEditor = groupProxyFields(nodes, nameInput, enabledInput, pools, resource);
  if (page === "auth-providers") {
    const hint = el("p", { class: "text-secondary", text: t.authentik_flow_hint });
    fields.append(hint);
    function updateProvider() {
      const authentik = nodes.provider.get() === "authentik";
      nodes.authentik_mode.element.hidden = !authentik;
      nodes.signin_url.element.hidden = authentik;
      nodes.signin_url.element.querySelector("input").required = !authentik && nodes.redirect_login.get();
      hint.hidden = !authentik;
    }
    nodes.provider.element.querySelector("select").addEventListener("change", updateProvider);
    nodes.redirect_login.element.querySelector("input").addEventListener("change", updateProvider);
    updateProvider();
  }
  if (
    ctx.role === "admin" &&
    [
      "dns-profiles",
      "crowdsec-profiles",
      "certificates",
      "geo-policies",
    ].includes(page)
  ) {
    const fieldNames =
      page === "geo-policies"
        ? ["account_id", "license_key"]
        : page === "crowdsec-profiles"
          ? ["api_key", "site_key", "secret_key"]
          : page === "certificates"
            ? ["eab_kid", "eab_hmac_key"]
            : [
                "username",
                "password",
                "iam_token",
                "service_account_id",
                "key_id",
                "private_key",
                "token",
                "domain_name",
                "project_id",
                "secret",
              ];
    const details = el("details", { class: "schema-group" }, [
      el("summary", { text: t.credentials }),
      el("p", { class: "text-secondary mt-2", text: t.credentials_hint }),
    ]);
    for (const key of fieldNames) {
      const input =
        key === "private_key"
          ? el("textarea", { class: "form-control mb-3", rows: 3 })
          : el("input", {
              type: "password",
              class: "form-control mb-3",
              autocomplete: "new-password",
            });
      credentialNodes[key] = input;
      details.append(
        el("label", { class: "form-label", text: key.replaceAll("_", " ") }),
        input,
      );
    }
    fields.append(details);
  }
  if (page === "access-lists") {
    fields.append(
      el("label", { class: "form-label", text: t.credentials }),
      el("p", { class: "text-secondary", text: t.basic_credentials_hint }),
      el("textarea", {
        id: "basic-credentials",
        class: "form-control",
        rows: 4,
        placeholder: "username=password",
      }),
    );
  }
  fields.prepend(el("a", { class: "d-block mb-3", href: `/ui/documentation/${page}`,
    text: t.read_documentation, target: "_blank", rel: "noopener" }));
}
async function upload(resource, ca = false) {
  let cert, key;
  openEditor(t.upload_certificate, async () => {
    const body = new FormData();
    body.append("certificate", cert.files[0]);
    if (key) body.append("private_key", key.files[0]);
    await api(
      `/api/v1/resources/${ca ? "client-cas" : "certificates"}/${resource.id}/upload`,
      { method: "POST", body },
    );
    dialog.close();
    message(t.operation_saved);
    await load();
  });
  cert = el("input", {
    type: "file",
    class: "form-control mb-3",
    required: "",
    accept: ".pem,.crt,.cer",
  });
  fields.append(
    el("label", { class: "form-label", text: t.certificates }),
    cert,
  );
  if (!ca) {
    key = el("input", {
      type: "file",
      class: "form-control",
      required: "",
      accept: ".pem,.key",
    });
    fields.append(
      el("label", { class: "form-label", text: t.private_key }),
      key,
    );
  }
}
async function dashboard() {
  const data = await api("/api/v1/dashboard");
  content.replaceChildren();
  const live = !!data.agent.available;
  content.append(
    el("div", { class: "agent-status" }, [
      el("span", { text: live ? t.agent_online : t.agent_offline }),
      el("span", {
        class: "operations-id",
        text: data.applied.generation
          ? `generation ${data.applied.generation}`
          : "—",
      }),
    ]),
  );
  const grid = el("div", { class: "dashboard-grid" });
  for (const kind of ["proxy-hosts", "streams", "certificates", "access-lists"])
    grid.append(
      el("div", { class: "card" }, [
        el("div", { class: "card-body" }, [
          el("div", { class: "stat-label", text: t[kind] }),
          el("div", {
            class: "stat-value",
            text: String(data.counts[kind] || 0),
          }),
          el("a", {
            href: `/ui/${kind}`,
            class: "small",
            text: t.details + " →",
          }),
        ]),
      ]),
    );
  content.append(grid);
  const capabilities = el("div", { class: "capability-grid" });
  for (const [name, info] of Object.entries(data.capabilities)) {
    if (typeof info !== "object" || !info || Array.isArray(info)) continue;
    capabilities.append(
      el(
        "div",
        { class: "capability", title: info.reason || info.verification || "" },
        [
          el("span", { text: name.replaceAll("_", " ") }),
          badge(info.supported ? "available" : t.not_supported),
        ],
      ),
    );
  }
  if (!capabilities.children.length)
    capabilities.append(el("p", { class: "text-secondary", text: t.unknown }));
  content.append(card(t.capabilities, capabilities));
}
async function resources() {
  const [rows, upstreams] = await Promise.all([
    api(`/api/v1/resources/${page}`),
    page === "proxy-hosts" ? api("/api/v1/resources/upstreams") : Promise.resolve([]),
  ]);
  const items = rows.map((resource) => {
    const actions = el("div", { class: "resource-actions" });
    if (
      ctx.role !== "observer" &&
      (ctx.role === "admin" || !ctx.admin_kinds.includes(page)) &&
      resource.source !== "docker"
    )
      actions.append(button(t.edit, () => editResource(resource)));
    if (ctx.role === "admin") {
      if (page === "certificates" && resource.data.mode !== "custom") {
        const renew = button(t.renew, async () => {
          renew.disabled = true;
          try {
            const operation = await api(`/api/v1/resources/certificates/${resource.id}/renew`, { method: "POST" });
            message(`${t.operation_saved} ${operation.operation_id}`);
            await load();
          } catch (error) {
            renew.disabled = false;
            throw error;
          }
        });
        renew.disabled = !!resource.active_operation || !resource.enabled;
        renew.dataset.action = "renew";
        actions.append(renew);
      }
      if (page === "certificates" || page === "client-cas")
        actions.append(
          button(t.upload, () => upload(resource, page === "client-cas")),
        );
      if (page === "geo-policies")
        actions.append(
          button(
            ctx.language === "ru" ? "Обновить MMDB" : "Update MMDB",
            async () => {
              await api(
                `/api/v1/resources/geo-policies/${resource.id}/update-database`,
                { method: "POST" },
              );
              message(t.operation_saved);
            },
          ),
        );
      if (page === "dns-profiles")
        actions.append(
          button(t.test_dns, async () => {
            await api(`/api/v1/resources/dns-profiles/${resource.id}/test`, {
              method: "POST",
            });
            message(t.operation_saved);
          }),
        );
      if (page === "ech")
        actions.append(
          button(
            ctx.language === "ru"
              ? "Проверить DNS и активировать"
              : "Confirm DNS and activate",
            async () => {
              await api(`/api/v1/resources/ech/${resource.id}/confirm-dns`, {
                method: "POST",
              });
              message(t.operation_saved);
            },
          ),
          button("Generate", async () => {
            await api(`/api/v1/resources/ech/${resource.id}/generate`, {
              method: "POST",
            });
            message(t.operation_saved);
          }),
        );
      if (resource.source !== "docker")
        actions.append(
          button(t.delete, async () => {
            if (!confirm(t.confirm_delete)) return;
            await api(`/api/v1/resources/${page}/${resource.id}`, {
              method: "DELETE",
              headers: { "If-Match": String(resource.version) },
            });
            message(t.operation_saved);
            await load();
          }),
        );
    }
    const details =
      (page === "ech" && resource.data.config
        ? `HTTPS: 1 . ech="${resource.data.config}"`
        : null) ||
      resource.data.domains?.join(", ") ||
      resource.data.zone ||
      (resource.data.host
        ? `${resource.data.host}:${resource.data.port}`
        : resource.id);
    if (page === "proxy-hosts") {
      const domain = resource.data.domains.find((name) => !name.startsWith("*."));
      const title = domain ? el("a", {
        class: "resource-title", text: resource.name, target: "_blank", rel: "noopener noreferrer",
        href: `${resource.ssl.configured ? "https" : "http"}://${domain.includes(":") ? `[${domain}]` : domain}/`,
      }) : el("span", { class: "resource-title", text: resource.name, title: t.wildcard_link });
      const destination = (route) => {
        const upstream = upstreams.find((group) => group.id === route.upstream_id);
        return route.upstream_id ? `${route.scheme}://${upstream?.name || "—"} (${t.upstreams})`
          : `${route.scheme}://${route.host.includes(":") ? `[${route.host}]` : route.host}:${route.port}`;
      };
      const forward = el("div", {}, [text(destination(resource.data))]);
      if (resource.data.locations.length) forward.append(el("details", { class: "route-details" }, [
        el("summary", { text: `${t.locations} (${resource.data.locations.length})` }),
        ...resource.data.locations.map((route) => el("div", { class: "resource-subtitle", text: `${route.path} → ${destination(route)}` })),
      ]));
      return [el("div", {}, [title, el("div", { class: "resource-subtitle", text: details }),
        ...(!domain ? [el("small", { class: "text-secondary", text: t.wildcard_link })] : [])]),
      forward, healthView(resource.health),
      el("div", {}, [text(resource.ssl.configured ? "HTTPS" : "HTTP"),
        ...(resource.ssl.configured && !resource.ssl.usable ? [el("small", { class: "d-block text-secondary", text: t.ssl_waiting })] : [])]),
      resource.ssl.configured ? certificateView(resource.certificate_info, false) : "—",
      badge(resource.enabled ? "enabled" : "disabled"), actions];
    }
    if (page === "certificates") return [
      el("div", {}, [el("div", { class: "resource-title", text: resource.name }),
        el("div", { class: "resource-subtitle", text: details }), badge(resource.enabled ? "enabled" : "disabled")]),
      badge(resource.active_operation?.status || resource.data.status),
      certificateView(resource.certificate_info), actions,
    ];
    return [
      el("div", {}, [
        el("div", { class: "resource-title", text: resource.name }),
        el("div", { class: "resource-subtitle", text: details }),
      ]),
      badge(
        resource.data.status || (resource.enabled ? "enabled" : "disabled"),
      ),
      badge(resource.source),
      String(resource.version),
      actions,
    ];
  });
  content.replaceChildren(
    table(page === "proxy-hosts" ? [t.name, t.destination, t.availability, "SSL", t.certificates, t.status, t.actions]
      : page === "certificates" ? [t.name, t.issuance, t.validity, t.actions]
      : [t.name, t.status, t.source, t.version, t.actions], items),
  );
}
function certificateView(info, dates = true) {
  const status = badge(info.status);
  status.textContent = t[`cert_${info.status}`] || info.status;
  const children = [status];
  if (dates && info.expires_at) children.push(
    el("div", { class: "resource-subtitle", text: `${t.valid_from}: ${new Date(info.not_before * 1000).toLocaleString(ctx.language)}` }),
    el("div", { class: "resource-subtitle", text: `${t.valid_until}: ${new Date(info.expires_at * 1000).toLocaleString(ctx.language)}` }),
    el("div", { class: "resource-subtitle", text: `${t.days_remaining}: ${info.remaining_days}` }),
  );
  return el("div", { "data-certificate-status": info.status }, children);
}
function healthView(health) {
  const children = [badge(health.status)];
  if (health.checked_at) children.push(el("div", { class: "resource-subtitle", text: `${t.checked_at}: ${new Date(health.checked_at * 1000).toLocaleTimeString(ctx.language)}` }));
  if (health.checks.length) children.push(el("details", { class: "route-details" }, [
    el("summary", { text: t.details }),
    ...health.checks.map((check) => el("div", { class: "resource-subtitle" }, [
      text(`${check.route_path} → ${check.host}:${check.port}${check.backup ? " (backup)" : ""}: `),
      badge(check.status), text(` · ${t[`reason_${check.reason}`] || check.reason}${check.http_status ? ` ${check.http_status}` : ""}`),
    ])),
  ]));
  return el("div", { "data-health-status": health.status }, children);
}
async function operations() {
  const rows = await api("/api/v1/operations");
  content.replaceChildren(
    table(
      [t.name, t.status, t.created, t.error],
      rows.map((job) => [
        el("div", {}, [
          el("div", { class: "resource-title", text: job.title }),
        ]),
        Object.assign(badge(job.status), { textContent: job.status_label }),
        new Date(job.created_at * 1000).toLocaleString(),
        el("div", {}, [el("div", { text: job.message }),
          job.next_step ? el("div", { class: "text-secondary", text: job.next_step }) : null,
          ...(job.warnings || []).map((warning) => el("div", { class: "text-warning",
            text: `${job.warnings_label}: ${warning.message}${warning.file ? ` · ${warning.file}:${warning.line}` : ""}` })),
          el("details", { class: "operation-technical" }, [el("summary", { text: t.technical_details }),
            el("small", { text: `${job.kind} · ${job.id}${job.error ? ` · ${job.error}` : ""}` })]),
        ]),
      ]),
    ),
  );
}
let safetyDeadline = 0;
let safetyRefreshing = false;
function safetyUnavailable(reason) {
  const box = document.getElementById("safety-notice");
  const description = reason === "agent_upgrade_required" ? t.safety_agent_upgrade : t.safety_unavailable;
  if (document.getElementById("safety-countdown")) {
    let warning = document.getElementById("safety-connection-warning");
    if (!warning) { warning = el("div", { id: "safety-connection-warning" }); box.append(warning); }
    warning.textContent = description;
    return;
  }
  box.className = "alert alert-warning";
  box.replaceChildren(el("strong", { text: t.safety_title }), el("div", { text: description }));
}
async function safetyStatus() {
  if (safetyRefreshing) return;
  safetyRefreshing = true;
  try {
    const state = await api("/api/v1/safety"), box = document.getElementById("safety-notice");
    if (state.available === false) { safetyUnavailable(state.reason); return; }
    if (state.status !== "awaiting_confirmation" && !state.halted) {
      safetyDeadline = 0;
      const enabled = state.enabled !== false;
      box.className = `alert ${enabled && state.watchdog_independent ? "alert-success" : "alert-warning"}`;
      const details = [el("strong", { text: enabled ? t.safety_enabled : t.safety_disabled })];
      if (enabled) details.push(el("div", {
        text: t.safety_ready.replace("{seconds}", state.timeout_seconds || 120),
      }));
      if (enabled && !state.watchdog_independent) details.push(el("div", { text: t.safety_watchdog_missing }));
      if (state.configuration_mismatch) details.push(el("div", { text: t.safety_configuration_mismatch }));
      box.replaceChildren(...details);
      return;
    }
    box.className = "alert alert-warning";
    if (state.halted) {
      safetyDeadline = 0;
      box.replaceChildren(el("strong", { text: t.safety_halted }), el("div", { text: t.safety_recovery }));
      return;
    }
    safetyDeadline = Date.now() + state.seconds_remaining * 1000;
    const countdown = el("strong", { id: "safety-countdown" });
    const checks = (state.checks || []).map((check) => el("div", {
      text: `${check.name}: ${check.ok ? t.safety_passed : t.safety_failed}`,
    }));
    checks.push(...(state.baseline || []).filter((check) => !check.ok).map((check) => el("div", {
      text: `${check.name}: ${t.safety_baseline_unavailable}`,
    })));
    const actions = [];
    if (state.can_manage && state.token) {
      const action = async (name) => {
        await api(`/api/v1/safety/${name}`, { method: "POST", body: JSON.stringify({
          revision_id: state.revision_id, token: state.token,
        }) });
        await safetyStatus();
        await load();
      };
      const confirm = button(t.safety_confirm, () => action("confirm"), true);
      confirm.disabled = !state.route_verified || !(state.checks || []).every((check) => check.ok);
      actions.push(confirm, text(" "), button(t.safety_rollback, () => action("rollback")));
      if (!state.route_verified) checks.push(el("div", { text: t.safety_open_panel }));
    }
    box.replaceChildren(el("div", {}, [text(t.safety_trial + " "), countdown]), ...checks,
      el("div", { class: "mt-2" }, actions));
    updateSafetyCountdown();
  } catch (_) {
    safetyUnavailable("agent_unavailable");
  } finally {
    safetyRefreshing = false;
  }
}
function updateSafetyCountdown() {
  const node = document.getElementById("safety-countdown");
  if (node) {
    const seconds = Math.max(0, Math.ceil((safetyDeadline - Date.now()) / 1000));
    node.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  }
}
async function users() {
  const rows = await api("/api/v1/users");
  content.replaceChildren(
    table(
      [t.email, "Role", t.status, "MFA", t.actions],
      rows.map((user) => [
        user.email,
        user.role,
        badge(user.enabled ? "enabled" : "disabled"),
        String(user.mfa_enabled),
        el("div", { class: "resource-actions" }, [
          button(t.edit, async () => {
            let role, subject, enabled;
            openEditor(t.edit, async () => {
              await api(`/api/v1/users/${user.id}`, {
                method: "PATCH",
                body: JSON.stringify({
                  role: role.value,
                  enabled: enabled.checked,
                  oidc_subject: subject.value || null,
                }),
              });
              dialog.close();
              await load();
            });
            role = el(
              "select",
              { class: "form-select mb-3" },
              ["admin", "operator", "observer"].map((value) =>
                el("option", { value, text: value }),
              ),
            );
            role.value = user.role;
            subject = el("input", {
              class: "form-control mb-3",
              placeholder: "issuer|subject",
            });
            subject.value = user.oidc_subject || "";
            enabled = el("input", {
              type: "checkbox",
              class: "form-check-input",
            });
            enabled.checked = user.enabled;
            fields.append(
              el("label", { class: "form-label", text: "Role" }),
              role,
              el("label", { class: "form-label", text: "OIDC issuer|subject" }),
              subject,
              el("label", { class: "form-label", text: t.enabled }),
              enabled,
            );
          }),
        ]),
      ]),
    ),
  );
}
async function createUser() {
  let nodes;
  openEditor(t.create, async () => {
    const data = Object.fromEntries(
      Object.entries(nodes).map(([key, node]) => [key, node.value]),
    );
    await api("/api/v1/users", { method: "POST", body: JSON.stringify(data) });
    dialog.close();
    await load();
  });
  nodes = {
    email: el("input", {
      type: "email",
      class: "form-control mb-3",
      required: "",
    }),
    password: el("input", {
      type: "password",
      class: "form-control mb-3",
      required: "",
      minlength: "12",
    }),
    role: el(
      "select",
      { class: "form-select mb-3" },
      ["observer", "operator", "admin"].map((value) =>
        el("option", { value, text: value }),
      ),
    ),
  };
  for (const [key, node] of Object.entries(nodes))
    fields.append(
      el("label", { class: "form-label", text: t[key] || key }),
      node,
    );
}
async function audit() {
  const rows = await api("/api/v1/audit");
  content.replaceChildren(
    table(
      [t.created, t.email, t.name, t.details],
      rows.map((a) => [
        new Date(a.created_at * 1000).toLocaleString(),
        a.actor,
        a.action,
        JSON.stringify(a.detail),
      ]),
    ),
  );
}
let refreshLogs = null;
async function logs() {
  if (refreshLogs) return refreshLogs();
  const initial = new URLSearchParams(location.search), controls = {}, wrappers = {};
  let active = new URLSearchParams(), offset = 0, sequence = 0, timer = null;
  const grid = el("div", { class: "log-filter-grid" }),
    form = el("form", { id: "log-filters" }, [grid]),
    results = el("div", { class: "log-results" }),
    summary = el("span", { class: "text-secondary", role: "status" }),
    warning = el("p", { class: "alert alert-warning mb-0", text: t.log_window }),
    updated = el("span", { class: "text-secondary" });
  warning.hidden = true;
  function select(options) {
    return el("select", { class: "form-select" }, options.map(([value, label]) =>
      el("option", { value, text: label })));
  }
  function field(key, label, node) {
    node.id = `log-${key}`;
    node.name = key;
    controls[key] = node;
    wrappers[key] = el("div", { class: `log-filter log-filter-${key}` }, [
      el("label", { class: "form-label", for: node.id, text: label }), node,
    ]);
    grid.append(wrappers[key]);
    if (initial.has(key)) node.value = initial.get(key);
    return node;
  }
  const kind = field("kind", t.log_source, select([
    ["access", t.log_access], ...(ctx.role === "admin" ? [["error", t.log_error]] : []),
  ]));
  if (!kind.value) kind.value = "access";
  field("q", t.log_search, el("input", {
    type: "search", class: "form-control", maxlength: "500", placeholder: t.log_search_hint,
  }));
  field("host", t.log_host, el("input", { class: "form-control", maxlength: "255", placeholder: "example.com" }));
  field("ip", "IP", el("input", { class: "form-control", maxlength: "255", placeholder: "192.0.2." }));
  field("method", t.log_method, select(["", "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "CONNECT", "TRACE"]
    .map((value) => [value, value || t.log_all])));
  field("status", t.log_status, el("input", {
    class: "form-control", placeholder: "404 / 4xx / 5xx", pattern: "[1-5]([0-9]{2}|xx)", maxlength: "3",
  }));
  field("level", t.log_level, select(["", "emerg", "alert", "crit", "error", "warn", "notice", "info", "debug"]
    .map((value) => [value, value || t.log_all])));
  for (const [key, label] of [["since", t.log_since], ["until", t.log_until]]) {
    const node = field(key, label, el("input", { type: "datetime-local", step: "1", class: "form-control" }));
    if (initial.has(key)) {
      const date = new Date(initial.get(key));
      if (!Number.isNaN(date.getTime())) {
        node.value = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
      }
    }
  }
  const limit = field("limit", t.log_limit, select([50, 100, 200, 500].map((value) => [value, String(value)])));
  if (!limit.value || !initial.has("limit")) limit.value = "200";
  const auto = el("input", { type: "checkbox", id: "log-auto", class: "form-check-input" }),
    submit = el("button", { type: "submit", class: "btn btn-primary", text: t.log_apply }),
    previous = button(t.log_newer, async () => {
      offset = Math.max(0, offset - Number(active.get("limit")));
      await refreshLogs();
    }),
    next = button(t.log_older, async () => {
      offset += Number(active.get("limit"));
      await refreshLogs();
    });
  previous.id = "log-newer";
  next.id = "log-older";
  function syncKind() {
    wrappers.status.hidden = kind.value !== "access";
    controls.status.disabled = kind.value !== "access";
    wrappers.level.hidden = kind.value !== "error";
    controls.level.disabled = kind.value !== "error";
  }
  function capture() {
    if (!form.reportValidity()) return false;
    if (controls.since.value && controls.until.value && controls.since.value > controls.until.value) {
      message(t.log_invalid_range, true);
      return false;
    }
    active = new URLSearchParams();
    for (const [key, node] of Object.entries(controls)) {
      if (key === "kind" || node.disabled || !node.value.trim()) continue;
      active.set(key, ["since", "until"].includes(key) ? new Date(node.value).toISOString() : node.value.trim());
    }
    active.set("kind", kind.value);
    offset = 0;
    return true;
  }
  refreshLogs = async () => {
    const request = ++sequence, params = new URLSearchParams(active), source = params.get("kind");
    params.delete("kind");
    params.set("offset", String(offset));
    results.setAttribute("aria-busy", "true");
    previous.disabled = next.disabled = true;
    try {
      const result = await api(`/api/v1/logs/${source}?${params}`);
      if (request !== sequence) return;
      if (offset && offset >= result.matched) {
        offset = Math.max(0, Math.floor((result.matched - 1) / result.limit) * result.limit);
        return refreshLogs();
      }
      document.getElementById("notice").classList.add("d-none");
      const cell = (value, className = "") => el("span", { class: className, text: String(value ?? "—") });
      const view = table(
        source === "access" ? [t.log_time, t.log_host, "IP", t.log_method, "URI", t.log_status]
          : [t.log_time, t.log_level, t.log_message],
        result.entries.map((row) => source === "access" ? [
          row.time || "—", cell(row.host), cell(row.ip, "font-monospace"), cell(row.method),
          cell(row.path ?? row.message, "log-message font-monospace"), cell(row.status),
        ] : [row.time || "—", cell(row.level), cell(row.message, "log-message font-monospace")]),
      );
      view.classList.add("log-table");
      if (!result.entries.length) view.querySelector(".empty-state").textContent =
        !result.exists || !result.scanned ? (source === "access" ? t.log_empty_access : t.log_empty_error)
          : t.log_no_matches;
      results.replaceChildren(view);
      summary.textContent = `${t.log_found}: ${result.matched} · ${t.log_shown}: ${result.entries.length ? offset + 1 : 0}–${offset + result.entries.length} · ${t.log_scanned}: ${result.scanned}`;
      warning.hidden = !result.truncated;
      previous.disabled = offset === 0;
      next.disabled = !result.has_more;
      updated.textContent = `${t.log_updated}: ${new Date().toLocaleTimeString()}`;
      const url = new URLSearchParams(active);
      if (offset) url.set("offset", String(offset));
      history.replaceState(null, "", `${location.pathname}?${url}`);
    } finally {
      if (request === sequence) results.setAttribute("aria-busy", "false");
    }
  };
  async function apply() {
    if (capture()) await refreshLogs();
  }
  const reset = button(t.log_reset, async () => {
    for (const [key, node] of Object.entries(controls)) if (key !== "kind") node.value = key === "limit" ? "200" : "";
    await apply();
  });
  reset.id = "log-reset";
  form.append(el("div", { class: "log-actions" }, [
    submit, reset,
    el("label", { class: "form-check mb-0" }, [auto, el("span", { class: "form-check-label", text: t.log_auto })]),
  ]));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    apply().catch((error) => message(error.message, true));
  });
  kind.addEventListener("change", () => {
    syncKind();
    apply().catch((error) => message(error.message, true));
  });
  auto.addEventListener("change", () => {
    clearInterval(timer);
    timer = auto.checked ? setInterval(() => {
      if (!document.hidden && offset === 0 && results.getAttribute("aria-busy") !== "true")
        refreshLogs().catch((error) => message(error.message, true));
    }, 5000) : null;
  });
  window.addEventListener("pagehide", () => clearInterval(timer), { once: true });
  content.replaceChildren(
    el("p", { class: "text-secondary", text: t.log_hint }), card(t.log_filters, form),
    el("div", { class: "log-summary" }, [summary, updated]), warning, results,
    el("div", { class: "log-pagination" }, [previous, next]),
  );
  syncKind();
  active = new URLSearchParams({ kind: kind.value, limit: limit.value });
  if (!capture()) return;
  const savedOffset = Number(initial.get("offset"));
  if (Number.isInteger(savedOffset) && savedOffset >= 0 && savedOffset <= 10000) offset = savedOffset;
  await refreshLogs();
}
let configurationFile = "";
let configurationRequest = 0;
async function configuration() {
  const request = ++configurationRequest;
  const result = await api("/api/v1/configuration");
  if (request !== configurationRequest) return;
  document.getElementById("notice").classList.add("d-none");
  const hint = el("p", { class: "text-secondary", text: t.config_hint });
  if (!result.revision_id || !result.files.length) {
    content.replaceChildren(hint, card(t.config_files, el("p", { class: "mb-0", text: t.config_empty })));
    return;
  }
  const selector = el("select", { id: "config-file", class: "form-select" });
  for (const file of result.files) selector.append(el("option", { value: file.path, text: file.path }));
  selector.value = result.files.some((file) => file.path === configurationFile)
    ? configurationFile : result.files[0].path;
  const code = el("code");
  const preview = el("pre", { id: "config-content", class: "config-preview", tabindex: "0",
    "aria-label": t.config_select }, [code]);
  const filename = el("div", { id: "config-path", class: "font-monospace config-path" });
  let selection = 0;
  async function showFile() {
    const selected = ++selection;
    configurationFile = selector.value;
    filename.textContent = selector.value;
    preview.setAttribute("aria-label", selector.value);
    code.textContent = t.loading;
    preview.setAttribute("aria-busy", "true");
    try {
      const query = new URLSearchParams({ revision_id: result.revision_id, path: selector.value });
      const file = await api(`/api/v1/configuration/file?${query}`);
      if (selected !== selection || request !== configurationRequest) return;
      code.textContent = file.content;
      preview.scrollTop = 0;
      preview.scrollLeft = 0;
    } catch (error) {
      if (selected === selection && request === configurationRequest) {
        code.textContent = "";
        message(error.message, true);
      }
    } finally {
      if (selected === selection) preview.setAttribute("aria-busy", "false");
    }
  }
  selector.addEventListener("change", showFile);
  content.replaceChildren(hint, card(t.config_files, el("div", { class: "config-viewer" }, [
    el("p", { class: "text-secondary config-revision" }, [text(`${t.config_revision}: `),
      el("span", { class: "font-monospace", text: result.revision_id })]),
    ...(result.mode === "existing" ? [el("p", { class: "text-secondary", text: t.config_existing })] : []),
    el("label", { for: "config-file", class: "form-label", text: t.config_file }), selector,
    filename, preview, el("small", { class: "text-secondary", text: t.config_sensitive }),
  ])));
  await showFile();
}
async function metrics() {
  const result = await api("/api/v1/metrics");
  const body = el("pre", {
    class: "import-report",
    text: JSON.stringify(result.latest, null, 2),
  });
  content.replaceChildren(
    card(t.metrics, body),
    el("a", {
      href: "/analytics/goaccess",
      class: "btn btn-outline-primary",
      text: "GoAccess",
    }),
  );
}
async function imports() {
  const body = el("div");
  const file = el("input", {
    class: "form-control mb-3",
    type: "file",
    accept: ".json,.zip",
  });
  const report = el("pre", { class: "import-report d-none" });
  let importId = null;
  body.append(
    file,
    button(t.preview, async () => {
      if (!file.files[0]) throw new Error("Select an exported archive");
      const form = new FormData();
      form.append("archive", file.files[0]);
      const result = await api("/api/v1/imports/preview", {
        method: "POST",
        body: form,
      });
      importId = result.import_id;
      report.textContent = JSON.stringify(result, null, 2);
      report.classList.remove("d-none");
    }),
    report,
    button(
      ctx.language === "ru"
        ? "Создать выключенные черновики"
        : "Create disabled drafts",
      async () => {
        if (!importId) throw new Error("Preview required");
        await api(`/api/v1/imports/${importId}/drafts`, { method: "POST" });
        message(t.operation_saved);
      },
    ),
    button(
      t.activate,
      async () => {
        if (!importId) throw new Error("Preview required");
        await api(`/api/v1/imports/${importId}/activate`, { method: "POST" });
        message(t.operation_saved);
      },
      true,
    ),
  );
  const backup = el("div", {}, [
    el("p", {
      class: "text-secondary",
      text:
        ctx.language === "ru"
          ? "Пароль архива задаётся локально: apm backup-password. Восстановление выполняется CLI при остановленных сервисах."
          : "Set an archive password locally: apm backup-password. Restore using the CLI while services are stopped.",
    }),
    button(t.backup, async () => {
      const result = await api("/api/v1/backups", { method: "POST" });
      message(`${t.operation_saved} ${result.backup_id}`);
    }),
  ]);
  content.replaceChildren(card(t.preview, body), card(t.backup, backup));
}
async function security() {
  const password = el("input", {
      type: "password",
      class: "form-control mb-3",
      placeholder: t.password,
    }),
    secret = el("pre", { class: "import-report d-none" }),
    code = el("input", { class: "form-control mb-3", placeholder: t.mfa });
  const body = el("div", {}, [
    password,
    button("Enable TOTP", async () => {
      const result = await api("/api/v1/auth/mfa/enroll", {
        method: "POST",
        body: JSON.stringify({ password: password.value }),
      });
      password.value = "";
      secret.textContent = result.uri;
      secret.classList.remove("d-none");
    }),
    secret,
    code,
    button(t.mfa_verify, async () => {
      const result = await api("/api/v1/auth/mfa/confirm", {
        method: "POST",
        body: JSON.stringify({ code: code.value }),
      });
      secret.textContent = result.recovery_codes.join("\n");
      secret.classList.remove("d-none");
      message(
        "Save recovery codes securely. They will not be displayed again.",
      );
    }),
  ]);
  content.replaceChildren(card("TOTP / MFA", body));
}
async function load() {
  if (page === "documentation") return;
  try {
    if (page === "dashboard") await dashboard();
    else if (page === "operations") await operations();
    else if (page === "users") await users();
    else if (page === "audit") await audit();
    else if (page === "imports") await imports();
    else if (page === "security") await security();
    else if (page === "logs") await logs();
    else if (page === "metrics") await metrics();
    else if (page === "configuration") await configuration();
    else await resources();
  } catch (error) {
    message(error.message, true);
  }
}
document.getElementById("refresh").addEventListener("click", load);
document
  .getElementById("create")
  ?.addEventListener("click", () =>
    editResource().catch((error) => message(error.message, true)),
  );
document
  .getElementById("create-user")
  ?.addEventListener("click", () =>
    createUser().catch((error) => message(error.message, true)),
  );
document.getElementById("logout").addEventListener("click", async () => {
  await api("/api/v1/auth/logout", { method: "POST" });
  location.assign("/login");
});
document.getElementById("language-switch").addEventListener("click", () => {
  document.cookie = `apm_language=${ctx.language === "ru" ? "en" : "ru"}; Path=/; SameSite=Strict`;
  location.reload();
});
document.getElementById("theme-switch").addEventListener("click", () => {
  const theme =
    document.documentElement.dataset.bsTheme === "dark" ? "light" : "dark";
  document.documentElement.dataset.bsTheme = theme;
  localStorage.setItem("apm_theme", theme);
});
document.documentElement.dataset.bsTheme =
  localStorage.getItem("apm_theme") || "light";
for (const id of ["editor-close", "editor-cancel"])
  document.getElementById(id).addEventListener("click", () => dialog.close());
document
  .getElementById("editor-form")
  .addEventListener("invalid", (event) => {
    const first = event.currentTarget.querySelector("input:invalid,select:invalid,textarea:invalid");
    if (event.target === first) editorReveal?.(event.target);
  }, true);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && activeFieldHelp) {
    event.preventDefault();
    event.stopPropagation();
    closeFieldHelp(true);
  }
}, true);
document.addEventListener("pointerdown", (event) => {
  if (activeFieldHelp && !activeFieldHelp.popup.contains(event.target)
    && !activeFieldHelp.trigger.contains(event.target)) closeFieldHelp();
}, true);
dialog.addEventListener("close", () => closeFieldHelp());
dialog.querySelector(".dialog-body").addEventListener("scroll", positionFieldHelp);
window.addEventListener("resize", positionFieldHelp);
document
  .getElementById("editor-form")
  .addEventListener("submit", async (event) => {
    event.preventDefault();
    const box = document.getElementById("editor-error");
    const save = document.getElementById("editor-save");
    save.disabled = true;
    try {
      await editorSubmit();
    } catch (error) {
      box.textContent = error.message;
      box.classList.remove("d-none");
      box.scrollIntoView({ block: "nearest" });
    } finally {
      save.disabled = false;
    }
  });
load();
safetyStatus();
setInterval(safetyStatus, 5000);
setInterval(updateSafetyCountdown, 1000);
if (["proxy-hosts", "certificates", "operations"].includes(page)) {
  let refreshing = false;
  setInterval(async () => {
    if (refreshing || dialog.open || document.hidden) return;
    refreshing = true;
    try { await load(); } finally { refreshing = false; }
  }, 5000);
}
