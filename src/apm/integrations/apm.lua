local M = {}
function M.init(path, observe, failure_action)
    local cs = require "crowdsec"
    local ok, err = cs.init(path, "apm/0.1")
    if not ok then error("CrowdSec initialization failed") end
    local original_ip = cs.allowIp
    cs.allowIp = function(ip)
        local allowed, remediation, failure = original_ip(ip)
        if failure and failure_action ~= "allow" then
            return false, "ban", failure
        end
        if observe and not allowed then
            ngx.log(ngx.NOTICE, "APM observed CrowdSec decision: ", tostring(remediation))
            return true, nil, failure
        end
        return allowed, remediation, failure
    end
    local original_appsec = cs.AppSecCheck
    cs.AppSecCheck = function(ip)
        local allowed, remediation, status, response, failure = original_appsec(ip)
        if failure and failure_action ~= "allow" then
            return false, "ban", ngx.HTTP_SERVICE_UNAVAILABLE, {}, failure
        end
        if observe and not allowed then
            ngx.log(ngx.NOTICE, "APM observed AppSec decision: ", tostring(remediation))
            return true, nil, ngx.HTTP_OK, {}, failure
        end
        return allowed, remediation, status, response, failure
    end
    return cs
end
return M
