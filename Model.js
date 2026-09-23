function defaultStatus() {
  return {
    ok: true,
    installed: false,
    binary: "",
    state: "missing-runtime",
    statusText: "Checking…",
    running: false,
    live: false,
    unit: "inactive",
    httpPort: 8080,
    amesPort: null,
    loom: 31,
    piersDir: "",
    active: "",
    ship: "",
    display: "",
    kind: "",
    pierPath: "",
    ready: false,
    lockPid: null,
    landscapeUrl: "http://127.0.0.1:8080",
    piers: [],
    logs: [],
    error: ""
  }
}

function parseStatus(raw) {
  var text = String(raw || "").trim()
  if (text === "") {
    var empty = defaultStatus()
    empty.ok = false
    empty.error = "Empty status from urbit-pier.py"
    empty.statusText = empty.error
    return empty
  }
  try {
    var parsed = JSON.parse(text)
    if (!parsed || typeof parsed !== "object") throw new Error("not an object")
    if (!Array.isArray(parsed.piers)) parsed.piers = []
    if (!Array.isArray(parsed.logs)) parsed.logs = []
    if (parsed.ok === false && !parsed.state) parsed.state = "error"
    if (!parsed.statusText) parsed.statusText = parsed.error || "Unavailable"
    return parsed
  } catch (e) {
    var failed = defaultStatus()
    failed.ok = false
    failed.state = "error"
    failed.error = "Failed to parse Urbit status"
    failed.statusText = failed.error
    return failed
  }
}

function expandHome(path, homeDir) {
  var value = String(path || "")
  var home = String(homeDir || "")
  if (value === "~") return home
  if (value.indexOf("~/") === 0) return home + value.substring(1)
  return value
}

function fileUrlToPath(url) {
  var value = String(url || "")
  if (value.indexOf("file://") === 0) {
    var path = value.substring(7)
    if (path.indexOf("localhost/") === 0) path = path.substring(9)
    try {
      return decodeURIComponent(path)
    } catch (e) {
      return path
    }
  }
  return value
}

function clampPoll(value) {
  var n = parseInt(String(value), 10)
  if (!isFinite(n)) n = 15
  if (n < 5) n = 5
  if (n > 120) n = 120
  return n
}

function kindLabel(kind) {
  var value = String(kind || "")
  if (value === "fake") return "Fake ship"
  if (value === "comet") return "Comet"
  if (value === "real") return "Keyfile ship"
  if (value === "attached") return "Existing pier"
  return "Pier"
}

function logText(logs, limit) {
  var rows = Array.isArray(logs) ? logs : []
  var start = Math.max(0, rows.length - (limit || 8))
  var slice = []
  for (var i = start; i < rows.length; i++) slice.push(String(rows[i] || ""))
  return slice.join("\n")
}

if (typeof module !== "undefined") {
  module.exports = {
    defaultStatus: defaultStatus,
    parseStatus: parseStatus,
    expandHome: expandHome,
    fileUrlToPath: fileUrlToPath,
    clampPoll: clampPoll,
    kindLabel: kindLabel,
    logText: logText
  }
}
