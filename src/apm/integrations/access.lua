-- Request enforcement stays inside Angie. No manager request is made here.
local ok, err = pcall(function()
    local allowed, remediation, error_message = _G.apm_cs.allowIp(ngx.var.remote_addr)
    if error_message and ngx.var.apm_crowdsec_failure ~= "allow" then
        return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end
    _G.apm_cs.Allow(ngx.var.remote_addr)
end)
if not ok then
    ngx.log(ngx.ERR, "APM CrowdSec request failed")
    if ngx.var.apm_crowdsec_failure ~= "allow" then
        return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end
end
