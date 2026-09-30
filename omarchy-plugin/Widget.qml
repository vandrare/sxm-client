import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import qs.Commons
import qs.Ui as Ui

Ui.BarWidget {
    id: root
    moduleName: "local.siriusxm"
    readonly property var service: bar?.shell?.serviceFor("local.siriusxm") ?? null
    readonly property var state: service ? service.state : ({})
    property bool opened: false
    property bool favoritesOnly: false
    property bool accountOpen: false
    function open() { opened = true }
    function close() { opened = false; password.text = "" }
    function closeForPopoutSwitch() { close() }
    function send(data) { if (service) service.send(data) }
    function login() {
        send({op: "login", username: username.text, password: password.text,
              region: region.value, remember: remember.checked})
        password.text = ""
    }
    readonly property var channels: {
        let needle = search.text.toLowerCase()
        return (state.channels || []).filter(function(c) {
            return (!root.favoritesOnly || (state.favorites || []).indexOf(c.id) >= 0)
                && (!needle || (c.number + " " + c.name).toLowerCase().indexOf(needle) >= 0)
        })
    }
    implicitWidth: bar && bar.vertical ? barSize : Math.min(220, label.implicitWidth + 24)
    implicitHeight: barSize
    Text {
        id: label
        anchors.centerIn: parent
        width: Math.min(196, implicitWidth)
        text: root.bar && root.bar.vertical ? "󰐊" : (root.state.playing ? "󰐊 " + (root.state.title || "SiriusXM") : "󰐊 SXM")
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: root.bar ? root.bar.barForeground : Color.foreground
        font.family: Style.font.family
        font.pixelSize: Style.font.body
    }
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.opened ? root.close() : root.open()
        onEntered: if (root.bar) root.bar.showTooltip(root, root.state.artist || "SiriusXM")
        onExited: if (root.bar) root.bar.hideTooltip(root)
    }
    Ui.KeyboardPanel {
        id: panel
        anchorItem: root
        owner: root
        bar: root.bar
        open: root.opened
        contentWidth: fittedContentWidth(440)
        contentHeight: fittedContentHeight(root.state.connected ? 620 : 410)
        focusTarget: root.state.connected ? search : username

        ColumnLayout {
            anchors.fill: parent
            spacing: 10
            Keys.onEscapePressed: root.close()
            RowLayout {
                Layout.fillWidth: true
                Text { text: "SiriusXM"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: 22; font.bold: true; Layout.fillWidth: true }
                Ui.Button { text: "Account"; visible: !!root.state.connected; focusable: true; onClicked: root.accountOpen = !root.accountOpen }
                Ui.Button { text: "×"; focusable: true; onClicked: root.close() }
            }
            Text {
                Layout.fillWidth: true
                text: root.state.busy ? "Signing in…" : root.state.connected ? "Connected · " + root.state.username : "Sign in to your streaming account"
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
                color: Color.muted
                font.pixelSize: Style.font.body
            }
            Text {
                Layout.fillWidth: true
                visible: text !== ""
                text: (root.service ? root.service.backendError : "Starting backend…") || root.state.error || root.state.notice || ""
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
                color: root.state.notice && !root.state.error ? Color.muted : Color.urgent
                font.pixelSize: Style.font.body
            }
            Ui.Button {
                visible: root.service !== null && !root.service.available
                text: "Restart backend"; focusable: true
                onClicked: root.service.restart()
            }
            ColumnLayout {
                visible: !root.state.connected
                Layout.fillWidth: true
                spacing: 10
                Ui.TextField { id: username; Layout.fillWidth: true; placeholderText: "Username or email"; text: root.state.username || ""; enabled: !root.state.busy }
                Ui.TextField { id: password; Layout.fillWidth: true; placeholderText: "Password"; password: true; enabled: !root.state.busy; onAccepted: root.login() }
                Ui.Dropdown { id: region; Layout.fillWidth: true; options: [{value: "US", label: "United States"}, {value: "CA", label: "Canada"}]; value: root.state.region || "US"; enabled: !root.state.busy; onChanged: function(value) { region.value = value } }
                Ui.Toggle { id: remember; Layout.fillWidth: true; label: "Remember me"; description: "Save password in desktop keyring"; checked: true; enabled: !root.state.busy; onClicked: checked = !checked }
                RowLayout {
                    Ui.Button { text: "Sign in"; bordered: true; focusable: true; enabled: !root.state.busy && username.text.trim() !== "" && password.text !== ""; onClicked: root.login() }
                    Ui.Button { text: "Cancel"; visible: !!root.state.busy; focusable: true; onClicked: root.send({op: "cancel"}) }
                    Ui.Button { text: "Forget account"; visible: !!root.state.username && !root.state.busy; focusable: true; onClicked: root.send({op: "forget"}) }
                }
            }
            RowLayout {
                visible: root.accountOpen && !!root.state.connected
                Ui.Button { text: "Sign out"; focusable: true; onClicked: root.send({op: "logout"}) }
                Ui.Button { text: "Forget account"; focusable: true; onClicked: root.send({op: "forget"}) }
            }
            ColumnLayout {
                visible: !!root.state.connected
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10
                Text { Layout.fillWidth: true; text: root.state.title || "Choose a channel"; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Color.foreground; font.pixelSize: 19; font.bold: true }
                Text { Layout.fillWidth: true; text: root.state.artist || ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: Color.muted; font.pixelSize: Style.font.body }
                RowLayout {
                    Ui.Button { text: root.state.paused ? "Resume" : "Pause"; focusable: true; enabled: !!root.state.playing; onClicked: root.send({op: "pause"}) }
                    Ui.Button { text: "Stop"; focusable: true; enabled: !!root.state.playing; onClicked: root.send({op: "stop"}) }
                    Ui.PanelSlider { id: volume; Layout.fillWidth: true; bar: root.bar; minimum: 0; maximum: 100; step: 1; integer: true; value: root.state.volume === undefined ? 70 : root.state.volume; onReleased: function(value) { root.send({op: "volume", value: Math.round(value)}) } }
                    Text { text: Math.round(volume.liveValue) + "%"; color: Color.foreground; font.pixelSize: 12 }
                }
                RowLayout {
                    Ui.TextField { id: search; Layout.fillWidth: true; placeholderText: "Search channels or numbers" }
                    Ui.Button { text: root.favoritesOnly ? "★ Favorites" : "☆ All"; focusable: true; onClicked: root.favoritesOnly = !root.favoritesOnly }
                }
                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 4
                    model: root.channels
                    Controls.ScrollBar.vertical: Controls.ScrollBar {}
                    delegate: RowLayout {
                        required property var modelData
                        width: ListView.view.width
                        Ui.Button {
                            Layout.fillWidth: true
                            text: modelData.number + "  " + modelData.name
                            leftAlign: true
                            selected: root.state.channel === modelData.id
                            focusable: true
                            onClicked: root.send({op: "play", channel: modelData.id})
                        }
                        Ui.Button { text: (root.state.favorites || []).indexOf(modelData.id) >= 0 ? "★" : "☆"; focusable: true; onClicked: root.send({op: "favorite", channel: modelData.id}) }
                    }
                }
                Text { visible: root.channels.length === 0; text: "No channels match."; color: Color.muted }
            }
            Item { visible: !root.state.connected; Layout.fillHeight: true }
        }
    }
}
