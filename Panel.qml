import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "ahlmark.urbit"
  ipcTarget: "ahlmark.urbit"
  manageIpc: false

  property string focusId: "header"
  property bool cursorActive: false
  property int phraseIndex: 0
  property string setupMode: ""
  property string cometName: "comet"
  property string keyShip: ""
  property string keyFile: ""
  property string keyName: ""
  property string attachPath: ""

  readonly property var activePhrases: [
    "Compiling Arvo",
    "Serving Landscape",
    "Watching Ames",
    "Hashing nock",
    "Keeping time",
    "Docking Vere",
    "Scribing desks",
    "Minding the loom"
  ]
  readonly property string heroPhraseText: activePhrases[phraseIndex % activePhrases.length]
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property bool lightGlyph: bar && bar.barForeground ? bar.barForeground.hslLightness > 0.55 : false
  readonly property string logoSource: Qt.resolvedUrl(lightGlyph ? "assets/urbit-logo-light.svg" : "assets/urbit-logo.svg")
  readonly property color iconColor: urbit.active ? foreground : dim
  readonly property color barIconColor: urbit.active ? barForeground : Qt.darker(barForeground, 1.55)
  readonly property bool headerHasCursor: cursorActive && focusId === "header" && urbit.installed && urbit.hasPier
  readonly property string toggleHint: urbit.active ? "Stop this ship" : (urbit.hasPier ? "Start this ship" : "Create a pier first")
  readonly property string heroMeta: {
    if (urbit.actionStatus !== "") return urbit.actionStatus
    if (urbit.live) return root.heroPhraseText
    return urbit.statusText || "Urbit"
  }
  readonly property string heroTitle: urbit.display || (urbit.installed ? "Urbit" : "Urbit")
  readonly property string heroDetail: urbit.hasPier ? Model.kindLabel(urbit.kind) : ""
  readonly property bool showSetup: !urbit.hasPier || setupMode !== ""
  readonly property bool formsLocked: urbit.busy || urbit.running
  property real chipPulse: 1.0
  readonly property real chipOpacity: urbit.live ? 1.0 : (urbit.starting ? chipPulse : 0.55)

  function visibleRowIds() {
    var rows = []
    if (urbit.installed && urbit.hasPier) rows.push("header")
    if (!urbit.installed) rows.push("install")
    if (urbit.live) rows.push("landscape")
    if (root.showSetup) {
      rows.push("fake")
      rows.push("comet")
      rows.push("key")
      rows.push("attach")
    } else {
      rows.push("add")
    }
    var piers = urbit.piers
    for (var i = 0; i < piers.length; i++) rows.push("pier:" + piers[i].id)
    return rows
  }

  function moveCursor(dx, dy) {
    cursorActive = true
    var rows = visibleRowIds()
    if (rows.length === 0) return
    var index = rows.indexOf(focusId)
    if (index < 0) {
      focusId = rows[0]
      return
    }
    if (dy === 0) return
    var next = Math.max(0, Math.min(rows.length - 1, index + dy))
    focusId = rows[next]
    scrollCursorIntoView()
  }

  function activateCursor() {
    var id = focusId
    if (id === "header") toggleRunning()
    else if (id === "install") urbit.installRuntime()
    else if (id === "landscape") urbit.openLandscape()
    else if (id === "fake") createFake()
    else if (id === "comet") submitComet()
    else if (id === "key") submitKey()
    else if (id === "attach") submitAttach()
    else if (id === "add") setupMode = "menu"
    else if (id.indexOf("pier:") === 0) selectPier(id.substring(5))
  }

  function toggleRunning() {
    if (urbit.installed && urbit.hasPier && !urbit.busy) urbit.toggleRunning()
  }

  function createFake() {
    if (formsLocked) return
    urbit.createFake()
    setupMode = ""
  }

  function submitComet() {
    if (formsLocked) return
    if (setupMode !== "comet") {
      setupMode = "comet"
      return
    }
    var name = cometName.trim() || "comet"
    urbit.bootComet(name)
    setupMode = ""
  }

  function submitKey() {
    if (formsLocked) return
    if (setupMode !== "key") {
      setupMode = "key"
      return
    }
    if (keyShip.trim() === "" || keyFile.trim() === "") {
      urbit.lastError = "Ship name and key file are required"
      urbit.actionStatus = urbit.lastError
      return
    }
    urbit.bootKey(keyShip.trim(), keyFile.trim(), keyName.trim())
    setupMode = ""
  }

  function submitAttach() {
    if (formsLocked) return
    if (setupMode !== "attach") {
      setupMode = "attach"
      return
    }
    if (attachPath.trim() === "") {
      urbit.lastError = "Pier path is required"
      urbit.actionStatus = urbit.lastError
      return
    }
    urbit.attach(attachPath.trim())
    setupMode = ""
  }

  function selectPier(id) {
    if (urbit.busy || urbit.running) return
    urbit.selectPier(id)
  }

  function scrollItemIntoView(item) {
    if (!panelFlick || !item) return
    Qt.callLater(function() {
      if (!item) return
      var margin = Style.space(6)
      var point = item.mapToItem(panelFlick.contentItem, 0, 0)
      var top = point.y
      var bottom = top + item.height
      var viewTop = panelFlick.contentY
      var viewBottom = viewTop + panelFlick.height
      var maxY = Math.max(0, panelFlick.contentHeight - panelFlick.height)
      if (top < viewTop + margin) panelFlick.contentY = Math.max(0, top - margin)
      else if (bottom > viewBottom - margin) panelFlick.contentY = Math.min(maxY, bottom + margin - panelFlick.height)
    })
  }

  function scrollCursorIntoView() {
    if (header && focusId === "header") scrollItemIntoView(header)
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onOpenedChanged: if (opened) {
    cursorActive = false
    if (panelFlick) panelFlick.contentY = 0
    urbit.refresh()
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  Service {
    id: urbit
    settings: root.settings
  }

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): string { urbit.refresh(); return "ok" }
    function start(): string { urbit.start(); return "ok" }
    function stop(): string { urbit.stop(); return "ok" }
    function status(): string { return urbit.statusText }
  }

  SequentialAnimation {
    running: urbit.starting
    loops: Animation.Infinite
    NumberAnimation { target: root; property: "chipPulse"; to: 0.35; duration: 700; easing.type: Easing.InOutQuad }
    NumberAnimation { target: root; property: "chipPulse"; to: 1.0; duration: 700; easing.type: Easing.InOutQuad }
    onStopped: root.chipPulse = 1.0
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    tooltipText: urbit.display ? (urbit.display + " — " + urbit.statusText) : urbit.statusText
    iconComponent: Component {
      Item {
        Image {
          anchors.centerIn: parent
          width: Style.space(12)
          height: Style.space(12)
          source: root.logoSource
          fillMode: Image.PreserveAspectFit
          sourceSize.width: width * 2
          sourceSize.height: height * 2
          opacity: root.chipOpacity
        }
      }
    }
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton || buttonCode === Qt.MiddleButton) urbit.refresh()
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(400))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(560))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onMoveRequested: function(dx, dy) {
        if (!root.cursorActive) { root.cursorActive = true; return }
        root.moveCursor(dx, dy)
      }
      onActivateRequested: if (root.cursorActive) root.activateCursor()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === "t" || t === "T") root.toggleRunning()
        else if (t === "r" || t === "R") urbit.refresh()
        else if (t === "l" || t === "L") urbit.openLandscape()
      }

      Flickable {
        id: panelFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: column
          width: panelFlick.width
          spacing: Style.space(12)

          Item {
            id: header
            visible: urbit.installed && urbit.hasPier
            width: parent.width
            implicitHeight: hero.implicitHeight
            readonly property bool ringVisible: root.headerHasCursor
            function focusHero() {
              root.cursorActive = true
              root.focusId = "header"
            }

            PanelHero {
              id: hero
              width: parent.width
              title: root.heroTitle
              meta: root.heroMeta
              detail: root.heroDetail
              foreground: root.foreground
              fontFamily: root.fontFamily
              iconOpacity: urbit.active ? 1.0 : 0.5
              iconComponent: Component {
                Image {
                  width: Style.font.display
                  height: Style.font.display
                  source: root.logoSource
                  fillMode: Image.PreserveAspectFit
                  sourceSize.width: width * 2
                  sourceSize.height: height * 2
                }
              }
              trailingControl: Component {
                ToggleSwitch {
                  id: powerSwitch
                  visible: urbit.installed && urbit.hasPier
                  checked: urbit.active
                  busy: urbit.busy
                  hasCursor: header.ringVisible
                  foreground: hero.foreground
                  onHovered: function(on) { if (on) header.focusHero() }
                  onToggled: root.toggleRunning()

                  PanelToolTip {
                    visible: powerSwitch.containsMouse
                    text: root.toggleHint
                    fontFamily: hero.fontFamily
                  }
                }
              }
            }
          }

          Text {
            visible: !urbit.hasPier
            width: parent.width
            text: urbit.installed ? "Create or attach a pier" : "Install Vere to run a local ship"
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
          }

          Text {
            visible: urbit.actionStatus !== "" || urbit.lastError !== "" || (!urbit.hasPier && urbit.statusText !== "")
            width: parent.width
            text: urbit.actionStatus !== "" ? urbit.actionStatus : (urbit.lastError !== "" ? urbit.lastError : urbit.statusText)
            color: urbit.lastError !== "" && urbit.actionStatus === "" ? root.urgent : root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
          }

          ActionRow {
            visible: !urbit.installed
            rowId: "install"
            title: urbit.busy && !urbit.installed ? "Installing Vere…" : "Install Vere"
            subtitle: "Download the live runtime from bootstrap.urbit.org"
            rowEnabled: !urbit.busy
            onActivated: urbit.installRuntime()
          }

          ActionRow {
            visible: urbit.live
            rowId: "landscape"
            title: "Open Landscape"
            subtitle: urbit.landscapeUrl
            onActivated: urbit.openLandscape()
          }

          PanelSeparator {
            visible: setupColumn.visible
            foreground: root.foreground
          }

          Column {
            id: setupColumn
            visible: root.showSetup
            width: parent.width
            spacing: Style.space(8)

            PanelSectionHeader {
              text: "NEW PIER"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            ActionRow {
              rowId: "fake"
              title: "Create fake ~zod"
              subtitle: "Local development ship, no live network"
              rowEnabled: !root.formsLocked
              onActivated: root.createFake()
            }

            ActionRow {
              rowId: "comet"
              title: "Mine a comet"
              subtitle: setupMode === "comet" ? "Enter a folder name, then create" : "Anonymous live-network identity"
              rowEnabled: !root.formsLocked
              onActivated: root.submitComet()
            }

            Column {
              visible: root.setupMode === "comet"
              width: parent.width
              spacing: Style.space(6)

              TextField {
                id: cometField
                width: parent.width
                foreground: root.foreground
                placeholderText: "Pier folder name"
                text: root.cometName
                onTextChanged: root.cometName = text
                onAccepted: root.submitComet()
              }

              Button {
                text: "Create comet"
                foreground: root.foreground
                enabled: !root.formsLocked
                onClicked: root.submitComet()
              }
            }

            ActionRow {
              rowId: "key"
              title: "Boot from keyfile"
              subtitle: setupMode === "key" ? "Ship name, then path to the .key file" : "Moon, planet, star, or galaxy"
              rowEnabled: !root.formsLocked
              onActivated: root.submitKey()
            }

            Column {
              visible: root.setupMode === "key"
              width: parent.width
              spacing: Style.space(6)

              TextField {
                width: parent.width
                foreground: root.foreground
                placeholderText: "Ship name (no ~)"
                text: root.keyShip
                onTextChanged: root.keyShip = text
              }

              TextField {
                width: parent.width
                foreground: root.foreground
                placeholderText: "Path to .key file"
                text: root.keyFile
                onTextChanged: root.keyFile = text
              }

              TextField {
                width: parent.width
                foreground: root.foreground
                placeholderText: "Pier folder name (optional)"
                text: root.keyName
                onTextChanged: root.keyName = text
                onAccepted: root.submitKey()
              }

              Button {
                text: "Boot from key"
                foreground: root.foreground
                enabled: !root.formsLocked
                onClicked: root.submitKey()
              }
            }

            ActionRow {
              rowId: "attach"
              title: "Attach existing pier"
              subtitle: setupMode === "attach" ? "Path to a folder that already contains .urb" : "Point at a pier directory you already have"
              rowEnabled: !root.formsLocked
              onActivated: root.submitAttach()
            }

            Column {
              visible: root.setupMode === "attach"
              width: parent.width
              spacing: Style.space(6)

              TextField {
                width: parent.width
                foreground: root.foreground
                placeholderText: "~/urbit/zod"
                text: root.attachPath
                onTextChanged: root.attachPath = text
                onAccepted: root.submitAttach()
              }

              Button {
                text: "Attach pier"
                foreground: root.foreground
                enabled: !root.formsLocked
                onClicked: root.submitAttach()
              }
            }
          }

          ActionRow {
            visible: urbit.hasPier && setupMode === ""
            rowId: "add"
            title: "Add another pier"
            subtitle: urbit.running ? "Stop the ship first" : "Fake ~zod, comet, keyfile, or attach"
            rowEnabled: !urbit.running && !urbit.busy
            onActivated: root.setupMode = "menu"
          }

          PanelSeparator {
            visible: urbit.piers.length > 0
            foreground: root.foreground
          }

          Column {
            visible: urbit.piers.length > 0
            width: parent.width
            spacing: Style.space(8)

            PanelSectionHeader {
              text: "PIERS"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Repeater {
              model: urbit.piers
              ActionRow {
                required property var modelData
                width: parent.width
                rowId: "pier:" + modelData.id
                title: modelData.display || modelData.id
                subtitle: Model.kindLabel(modelData.kind) + " · " + modelData.path
                current: modelData.active === true
                rowEnabled: !urbit.running && !urbit.busy
                onActivated: root.selectPier(modelData.id)
              }
            }
          }

          Column {
            visible: (urbit.starting || urbit.lastError !== "") && urbit.logs.length > 0
            width: parent.width
            spacing: Style.space(6)

            PanelSeparator { foreground: root.foreground }

            PanelSectionHeader {
              text: "LOG"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Text {
              width: parent.width
              text: Model.logText(urbit.logs, 8)
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WrapAnywhere
            }
          }
        }
      }
    }
  }

  Timer {
    id: phraseTimer
    interval: 2800
    running: root.opened && urbit.live
    repeat: true
    onTriggered: phraseSwap.restart()
  }

  SequentialAnimation {
    id: phraseSwap
    PropertyAnimation {
      target: hero
      property: "metaOpacity"
      to: 0.0
      duration: 180
      easing.type: Easing.OutQuad
    }
    ScriptAction {
      script: root.phraseIndex = (root.phraseIndex + 1) % root.activePhrases.length
    }
    PropertyAnimation {
      target: hero
      property: "metaOpacity"
      to: 1.0
      duration: 260
      easing.type: Easing.InQuad
    }
  }

  component ActionRow: CursorSurface {
    id: actionRow
    property string rowId: ""
    property string title: ""
    property string subtitle: ""
    property bool rowEnabled: true
    signal activated()

    width: parent ? parent.width : implicitWidth
    hasCursor: root.cursorActive && root.focusId === rowId
    current: false
    foreground: root.foreground
    implicitHeight: actionLabels.implicitHeight + Style.spacing.rowPaddingX
    opacity: rowEnabled ? 1.0 : 0.5

    MouseArea {
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: actionRow.rowEnabled ? Qt.PointingHandCursor : Qt.ArrowCursor
      enabled: actionRow.rowEnabled
      onEntered: {
        root.cursorActive = true
        root.focusId = actionRow.rowId
      }
      onClicked: actionRow.activated()
    }

    Column {
      id: actionLabels
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: Style.space(10)
      anchors.rightMargin: Style.space(10)
      spacing: Style.space(1)

      Text {
        width: parent.width
        text: actionRow.title
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        elide: Text.ElideRight
      }

      Text {
        visible: actionRow.subtitle !== ""
        width: parent.width
        text: actionRow.subtitle
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        wrapMode: Text.WordWrap
      }
    }
  }
}
