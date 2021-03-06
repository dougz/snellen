goog.require("goog.dom");
goog.require("goog.dom.classlist");
goog.require("goog.events");
goog.require("goog.net.XhrIo");
goog.require("goog.json.Serializer");

function show_team(e) {
    var el = goog.dom.getElement("teamselect");

    var t = team_data[el.value];
    if (t) {
        goog.dom.getElement("enable").disabled = false;
        goog.dom.getElement("location").innerHTML = t.location;
        goog.dom.getElement("phone").innerHTML = t.phone;
        goog.dom.getElement("phone").href = "tel:" + t.phone;
    } else {
        goog.dom.getElement("enable").disabled = true;
        goog.dom.getElement("location").innerHTML = "";
        goog.dom.getElement("phone").innerHTML = "";
        goog.dom.getElement("phone").href = "";
    }
    goog.dom.getElement("complete").disabled = true;
}

function enable() {
    var el = goog.dom.getElement("complete");
    el.disabled = !el.disabled;
}

function complete() {
    var el = goog.dom.getElement("teamselect");
    var t = team_data[el.value];

    var d = /** @type{Complete} */ ({action: "complete_task",
                                     which: "done",
                                     immediate: true,
                                     key: t.key})
    var ser = new goog.json.Serializer();
    goog.net.XhrIo.send("/admin/action", result, "POST",
                        ser.serialize(d));
}

function result(e) {
    var code = e.target.getStatus();
    var el = goog.dom.getElement("result");
    if (code == 204) {
        el.innerHTML = "success!";
        goog.dom.classlist.add(el, "success");
    } else {
        el.innerHTML = e.target.getResponseText();
        goog.dom.classlist.remove(el, "success");
    }
    goog.dom.getElement("enable").disabled = true;
    goog.dom.getElement("complete").disabled = true;
}

function reload() {
    location.reload(true);
}

window.onload = function() {
    var el;

    el = goog.dom.getElement("teamselect");
    if (el) goog.events.listen(el, goog.events.EventType.CHANGE, show_team);
    el = goog.dom.getElement("enable");
    if (el) goog.events.listen(el, goog.events.EventType.CLICK, enable);
    el = goog.dom.getElement("complete");
    if (el) goog.events.listen(el, goog.events.EventType.CLICK, complete);
    el = goog.dom.getElement("reload");
    if (el) goog.events.listen(el, goog.events.EventType.CLICK, reload);
}
