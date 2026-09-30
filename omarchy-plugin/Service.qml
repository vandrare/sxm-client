import QtQuick
import Quickshell
import Quickshell.Io

Item {
    id: root
    property var shell: null
    property var state: ({connected: false, busy: false, channels: [], favorites: [], volume: 70})
    property bool available: false
    property string backendError: ""
    function send(data) {
        if (!available) { backendError = "Backend is not running. Click Restart backend."; return }
        backend.write(JSON.stringify(data) + "\n")
    }
    function restart() {
        backendError = ""
        backend.running = true
    }
    Process {
        id: backend
        command: [Qt.resolvedUrl("launch-backend").toString().replace(/^file:\/\//, "")]
        stdinEnabled: true
        running: true
        onStarted: { root.available = true; root.backendError = "" }
        stdout: SplitParser {
            onRead: function(line) {
                try { root.state = JSON.parse(line) } catch (e) { root.backendError = "Invalid backend response." }
            }
        }
        stderr: SplitParser { onRead: function(line) {} }
        onExited: {
            root.available = false
            root.backendError = "Backend stopped. Click Restart backend."
        }
    }
    Component.onDestruction: backend.stdinEnabled = false
}
