goog.require("goog.dom");
goog.require("goog.events");
goog.require("goog.net.XhrIo");
goog.require("goog.json.Serializer");
goog.require("goog.i18n.DateTimeFormat");

function alter_role(e) {
    var n = e.target.id.search("::");
    var user = e.target.id.substring(0, n);
    var role = e.target.id.substring(n+2);

    goog.net.XhrIo.send("/" + (e.target.checked ? "set" : "clear") + "_admin_role/" + user + "/" + role,
			function(e) {
			    var xhr = e.target;
			    if (xhr.getStatus() != 204) {
				alert("Updating " + user + " " + role + " failed: " + xhr.getResponseText());
			    }
			});
}


function activate_role_checkboxes() {
    var cbs = document.querySelectorAll("table#user-roles input[type='checkbox']");
    for (var i = 0; i < cbs.length; ++i) {
	var cb = cbs[i];
	goog.events.listen(cb, goog.events.EventType.CHANGE, alter_role);
    }
}

function send_hint_reply() {
    var serializer = new goog.json.Serializer();
    var text = goog.dom.getElement("replytext");
    console.log(text);
    text = text.value;
    console.log(text);
    if (!text) return;
    goog.net.XhrIo.send("/hintreply", function(e) {
    	var code = e.target.getStatus();
    	if (code != 204) {
    	    alert(e.target.getResponseText());
    	}
    }, "POST", serializer.serialize({"team_username": team_username, "puzzle_id": puzzle_id, "text": text}));
}


function enable_hint_reply() {
    var b = goog.dom.getElement("hintreply");
    goog.events.listen(b, goog.events.EventType.CLICK, send_hint_reply);
}

goog.exportSymbol("activate_role_checkboxes", activate_role_checkboxes);
goog.exportSymbol("enable_hint_reply", enable_hint_reply)




