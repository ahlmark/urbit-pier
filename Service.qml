import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import "Model.js" as Model

Item {
  id: root

  property var settings: ({})

  property var payload: Model.defaultStatus()
  property int _desired: -1
  property bool refreshing: false
  property string actionStatus: ""
  property string lastError: ""
  property string _statusOutput: ""
  property string _statusError: ""
  property string _controlOutput: ""
  property string _controlError: ""

  readonly property string homeDir: Quickshell.env("HOME") || ""
  readonly property string helper: Model.fileUrlToPath(Qt.resolvedUrl("urbit-pier.py"))
  readonly property string configFile: Model.expandHome(setting("configFile", "~/.config/omarchy/urbit.json"), homeDir)
  readonly property int pollSeconds: Model.clampPoll(setting("pollSeconds", 15))
  readonly property bool installed: payload.installed === true
  readonly property string state: String(payload.state || "missing-runtime")
  readonly property bool running: payload.running === true
  readonly property bool live: payload.live === true
  readonly property bool starting: state === "starting" || (_desired === 1 && !live)
  readonly property bool active: _desired === -1 ? (running || live || state === "starting") : (_desired === 1)
  readonly property bool busy: statusProcess.running || controlProcess.running
  readonly property string statusText: String(payload.statusText || lastError || "")
  readonly property string display: String(payload.display || "")
  readonly property string landscapeUrl: String(payload.landscapeUrl || "http://127.0.0.1:8080")
  readonly property var piers: payload.piers || []
  readonly property var logs: payload.logs || []
  readonly property bool hasPier: !!payload.active
  readonly property string kind: String(payload.kind || "")
  readonly property string pierPath: String(payload.pierPath || "")
  readonly property int httpPort: Number(payload.httpPort || 8080)

  function setting(name, fallback) {
    var value = settings ? settings[name] : undefined
    return value === undefined || value === null || value === "" ? fallback : value
  }

  function helperCmd(action, extra) {
    var cmd = ["python3", root.helper, action, "--config", root.configFile]
    if (extra && extra.length) {
      for (var i = 0; i < extra.length; i++) cmd.push(String(extra[i]))
    }
    return cmd
  }

  function refresh() {
    if (statusProcess.running || helper === "") return
    _statusOutput = ""
    _statusError = ""
    refreshing = true
    statusProcess.command = helperCmd("status")
    statusProcess.running = true
  }

  function applyStatus(raw) {
    var parsed = Model.parseStatus(raw)
    payload = parsed
    if (parsed.ok === false) {
      lastError = parsed.error || parsed.statusText || "Failed to read Urbit status"
      return
    }
    if (parsed.state === "error" && parsed.error) lastError = String(parsed.error)
    else lastError = ""
    if (_desired !== -1) {
      var wantOn = _desired === 1
      var isOn = parsed.running === true || parsed.live === true || parsed.state === "starting"
      if (wantOn === isOn && parsed.state !== "starting") _desired = -1
      if (!wantOn && !isOn) _desired = -1
    }
  }

  function elideStatus(text) {
    var value = String(text || "").replace(/\s+/g, " ").trim()
    return value.length > 160 ? value.substring(0, 157) + "…" : value
  }

  function runControl(action, extra, desired) {
    if (controlProcess.running) return
    if (desired !== undefined && desired !== null) _desired = desired
    _controlOutput = ""
    _controlError = ""
    actionStatus = ""
    controlProcess.command = helperCmd(action, extra)
    controlProcess.running = true
  }

  function installRuntime() { runControl("install-runtime") }
  function createFake() { runControl("create-fake", ["--ship", "zod"]) }
  function bootComet(name) { runControl("boot-comet", ["--name", name || "comet"]) }
  function bootKey(ship, key, name) {
    var extra = ["--ship", ship, "--key", key]
    if (name) extra.push("--name", name)
    runControl("boot-key", extra)
  }
  function attach(path) { runControl("attach", ["--path", path]) }
  function selectPier(id) { runControl("select", ["--id", id]) }
  function start() { runControl("start", [], 1) }
  function stop() { runControl("stop", [], 0) }

  function toggleRunning() {
    if (busy) return
    if (!installed) {
      installRuntime()
      return
    }
    if (!hasPier) return
    if (active) stop()
    else start()
  }

  function openLandscape() {
    if (!landscapeUrl) return
    Qt.openUrlExternally(landscapeUrl)
  }

  Timer {
    id: refreshTimer
    interval: (root.state === "starting" ? 2 : root.pollSeconds) * 1000
    repeat: true
    running: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  Timer {
    id: delayedRefresh
    interval: 800
    repeat: false
    onTriggered: root.refresh()
  }

  Timer {
    id: actionStatusTimer
    interval: 2400
    repeat: false
    onTriggered: root.actionStatus = ""
  }

  Timer {
    id: settleTimer
    property int ticks: 0
    interval: 1500
    repeat: true
    running: false
    onTriggered: {
      settleTimer.ticks += 1
      root.refresh()
      if (settleTimer.ticks >= 8) {
        settleTimer.ticks = 0
        settleTimer.running = false
      }
    }
  }

  Process {
    id: statusProcess
    running: false
    command: []
    stdout: StdioCollector { id: statusStdout; waitForEnd: true; onStreamFinished: root._statusOutput = text }
    stderr: StdioCollector { id: statusStderr; waitForEnd: true; onStreamFinished: root._statusError = text }
    onExited: function(exitCode) {
      root.refreshing = false
      var stdout = String(statusStdout.text || root._statusOutput || "")
      var stderr = String(statusStderr.text || root._statusError || "")
      if (stdout.trim() !== "") root.applyStatus(stdout)
      else {
        root.lastError = root.elideStatus(stderr || "Could not read Urbit status")
        root.payload = Model.parseStatus("")
      }
    }
  }

  Process {
    id: controlProcess
    running: false
    command: []
    stdout: StdioCollector { id: controlStdout; waitForEnd: true; onStreamFinished: root._controlOutput = text }
    stderr: StdioCollector { id: controlStderr; waitForEnd: true; onStreamFinished: root._controlError = text }
    onExited: function(exitCode) {
      var stdout = String(controlStdout.text || root._controlOutput || "")
      var stderr = String(controlStderr.text || root._controlError || "")
      var parsed = stdout.trim() !== "" ? Model.parseStatus(stdout) : null
      if (parsed && parsed.ok !== false) {
        root.applyStatus(stdout)
        root.lastError = parsed.state === "error" ? String(parsed.error || parsed.statusText || "") : ""
        root.actionStatus = root.lastError === "" ? "" : root.lastError
      } else {
        var message = (parsed && parsed.error) ? parsed.error : (stderr || stdout || "Urbit command failed")
        root._desired = -1
        root.lastError = root.elideStatus(message)
        root.actionStatus = root.lastError
      }
      if (root.actionStatus !== "") actionStatusTimer.restart()
      settleTimer.ticks = 0
      settleTimer.restart()
      delayedRefresh.restart()
    }
  }
}
