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


function activateRoleCheckboxes() {
    var cbs = document.querySelectorAll("table#user-roles input[type='checkbox']");
    for (var i = 0; i < cbs.length; ++i) {
	var cb = cbs[i];
	goog.events.listen(cb, goog.events.EventType.CHANGE, alter_role);
    }
}

goog.exportSymbol("activateRoleCheckboxes", activateRoleCheckboxes);




