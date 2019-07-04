goog.require("goog.dom");
goog.require("goog.dom.classlist");
goog.require("goog.events");
goog.require("goog.net.XhrIo");
goog.require("goog.ui.ModalPopup");
goog.require("goog.json.Serializer");
goog.require("goog.i18n.DateTimeFormat");

class Waiter {
    constructor(dispatcher) {
	/** @type{goog.net.XhrIo} */
	this.xhr = new goog.net.XhrIo();
	/** @type{goog.net.XhrIo} */
	this.other_xhr = new goog.net.XhrIo();
	/** @type{number} */
	this.serial = 0;
	/** @type{number} */
	this.backoff = 100;

	/** @type(Dispatcher) */
	this.dispatcher = dispatcher;
    }

    waitcomplete() {
        if (this.xhr.getStatus() == 401) {
            return;
        }

        if (this.xhr.getStatus() != 200) {
            this.backoff = Math.min(10000, Math.floor(this.backoff*1.5));

	    // XXX cancel early for development
	    if (this.backoff > 1000) {
		console.log("aborting retries");
		return;
	    }

            setTimeout(goog.bind(this.xhr.send, this.xhr, "/wait/" + this.serial),
                       this.backoff);
            return;
        }

        this.backoff = 100;

	var msgs = /** @type{Array<Object>} */ (this.xhr.getResponseJson());
	for (var i = 0; i < msgs.length; ++i) {
	    this.serial = /** @type{number} */ (msgs[i][0]);
	    var msg = /** @type{Message} */ (msgs[i][1]);
	    this.dispatcher.dispatch(msg);
	}

        var temp = this.xhr;
        this.xhr = this.other_xhr;
        this.other_xhr = temp;
        this.xhr.send("/wait/" + this.serial);
    }

    start() {
	goog.events.listen(this.xhr, goog.net.EventType.COMPLETE, this.waitcomplete, false, this);
	goog.events.listen(this.other_xhr, goog.net.EventType.COMPLETE, this.waitcomplete, false, this);
	this.xhr.send("/wait/" + this.serial);
    }
}

class Dispatcher {
    constructor() {
	this.methods = {
	    "history_change": this.history_change,
	    "solve": this.solve,
	    "open": this.open,
	}
    }

    /** @param{Message} msg */
    dispatch(msg) {
	this.methods[msg.method](msg);
    }

    /** @param{Message} msg */
    history_change(msg) {
	if (msg.puzzle_id == puzzle_id) {
	    submit_dialog.update_history();
	}
    }

    /** @param{Message} msg */
    solve(msg) {
	toast_manager.add_toast("<b>" + msg.title + "</b> was solved!", 5000);
    }

    /** @param{Message} msg */
    open(msg) {
	toast_manager.add_toast("<b>" + msg.title + "</b> is now open!", 5000);
    }
}

class TimeFormatter {
    constructor() {
	this.formatter = new goog.i18n.DateTimeFormat("EEE h:mm:ss aa");
    }
    format(t) {
	var d = new Date(t * 1000);
	var txt = this.formatter.format(d);
	var l = txt.length;
	return txt.substr(0, l-2) + txt.substr(l-2, 2).toLowerCase();
    }
    duration(s) {
	var min = Math.trunc(s/60);
	var sec = Math.trunc(s%60);
	return "" + min + ":" + (""+sec).padStart(2, "0");
    }
}

class SubmitDialog {
    constructor() {
	/** @type{boolean} */
	this.built = false;
	/** @type{Object|undefined} */
	this.serializer = null;
	/** @type{Object|undefined} */
	this.dialog = null;
	/** @type{Element|undefined} */
	this.input = null;
	/** @type{Element|undefined} */
	this.submit_div = null;
	/** @type{?Element} */
	this.top_note = null;

	/** @type{?Element} */
	this.history = null;

	/** @type{number|null} */
	this.timer = null;
	/** @type{Array} */
	this.counters = null;
    }

    build() {
	this.serializer = new goog.json.Serializer();

	this.dialog = new goog.ui.ModalPopup();
	this.dialog.render();

	var content =  this.dialog.getContentElement();

	this.top_note = goog.dom.createDom("SPAN");
	this.top_note.style.display = "none";
	content.appendChild(this.top_note);

	this.history = goog.dom.createDom("TABLE", {"class": "submissions"});
	content.appendChild(this.history);

	this.submit_div = goog.dom.createDom("DIV");

	this.input = goog.dom.createDom("INPUT", {id: "answer", "name": "answer"}, "");
	this.submit_div.appendChild(this.input);
	goog.events.listen(this.input, goog.events.EventType.KEYDOWN, goog.bind(this.onkeydown, this));

	var b = goog.dom.createDom("BUTTON", null, "Submit");
	goog.events.listen(b, goog.events.EventType.CLICK, goog.bind(this.submit, this));
	this.submit_div.appendChild(b);

	content.appendChild(this.submit_div);

	b = goog.dom.createDom("BUTTON", null, "Close");
	content.appendChild(b);
	goog.events.listen(b, goog.events.EventType.CLICK, goog.bind(this.close, this));

	this.built = true;

	this.update_history();
    }

    update_history() {
	if (!this.built) return;
	if (!this.dialog.isVisible()) return;
	goog.net.XhrIo.send("/submit_history/" + puzzle_id, goog.bind(function(e) {
	    var code = e.target.getStatus();
	    if (code == 200) {
		var response = /** type{SubmissionHistory} */ (e.target.getResponseJson());
		this.render_history(response);
		if (response.allowed) {
		    this.submit_div.style.display = "block";
		} else {
		    this.submit_div.style.display = "none";
		}
	    }
	}, this));
    }

    /** @param{SubmissionHistory} response */
    render_history(response) {
	if (this.timer) {
	    clearInterval(this.timer);
	    this.timer = null;
	}
	this.counters = [];

	if (response.total) {
	    this.top_note.innerHTML = response.correct + "/" + response.total + " correct answer(s) found";
	    this.top_note.style.display = "inline";
	} else {
	    this.top_note.style.display = "none";
	}

	this.history.innerHTML = "";

	this.history.appendChild(
	    goog.dom.createDom("TR", null,
			       goog.dom.createDom("TH", {className: "submit-time"}, "time"),
			       goog.dom.createDom("TH", {className: "submit-state"}, "result"),
			       goog.dom.createDom("TH", {className: "submit-answer"}, "submission")));


	if (response.history.length == 0) {
	    this.history.appendChild(
		goog.dom.createDom("TR", null,
				   goog.dom.createDom("TD", {className: "submit-empty", colSpan: 3},
						      "No submissions for this puzzle.")));
	}

	var cancelsub = function(sub) {
	    return function() {
		goog.net.XhrIo.send("/submit_cancel/" + puzzle_id + "/" + sub.submit_id);
	    };
	};

	for (var i = 0; i < response.history.length; ++i) {
	    var sub = response.history[i];
	    var el = null;
	    if (sub.state == "pending") {
		el = goog.dom.createDom("SPAN", {className: "submit-timer"});
		this.counters.push([sub.check_time, el])
	    }

	    var answer = null;
	    if (sub.state == "pending") {
		var link = goog.dom.createDom("A", {className: "submit-cancel"}, "\u00d7");
		goog.events.listen(link, goog.events.EventType.CLICK, cancelsub(sub));
		answer = [link, sub.answer];
	    } else {
		answer = sub.answer;
	    }

	    var tr = goog.dom.createDom(
		"TR", null,
		goog.dom.createDom("TD", {className: "submit-time"},
				   time_formatter.format(sub.submit_time)),
		goog.dom.createDom("TD", {className: "submit-state"},
				   el,
				   goog.dom.createDom("SPAN", {className: "submit-" + sub.state},
						      sub.state)),
		goog.dom.createDom("TD", {className: "submit-answer"},
				   answer));
	    this.history.appendChild(tr);

	    if (sub.response) {
		var td = goog.dom.createDom("TD", {className: "submit-extra",
						   colSpan: 3});
		td.innerHTML = sub.response;
		this.history.appendChild(goog.dom.createDom("TR", null, td));
	    }
	}
	this.dialog.reposition();

	if (this.counters.length > 0) {
	    this.update_counters();
	    this.timer = setInterval(goog.bind(this.update_counters, this), 1000);
	}
    }

    update_counters() {
	var now = (new Date()).getTime() / 1000.0;
	for (var i = 0; i < this.counters.length; ++i) {
	    var check_time = this.counters[i][0] + 1.0;
	    var el = this.counters[i][1];
	    var remain = null;
	    if (check_time > now) {
		remain = time_formatter.duration(check_time - now);
	    } else {
		remain = "0:00";
	    }
	    el.innerText = remain;
	}
    }


    submit() {
	var answer = this.input.value;
	if (answer == "") return;
	this.input.value = "";
	goog.net.XhrIo.send("/submit", function(e) {
	    var code = e.target.getStatus();
	    if (code != 204) {
		alert(e.target.getResponseText());
	    }
	}, "POST", this.serializer.serialize({"puzzle_id": puzzle_id, "answer": answer}));
    }

    onkeydown(e) {
	if (e.keyCode == goog.events.KeyCodes.ENTER) {
	    this.submit();
	    e.preventDefault();
	}
    }

    show() {
	if (!this.built) this.build();
	this.dialog.setVisible(true);
	this.update_history();
	this.input.focus();
	return false;
    }

    close() {
	this.dialog.setVisible(false);
	if (this.timer) {
	    clearInterval(this.timer);
	    this.timer = null;
	}
    }
}

class ToastManager {
    constructor() {
	/** @type{Element} */
	this.toasts_div = goog.dom.createDom("DIV", {className: "toasts"});
	document.body.appendChild(this.toasts_div);

	/** @type{number} */
	this.toasts = 0;
	/** @type{Array<Element>} */
	this.dead_toasts = [];
    }

    add_toast(message, timeout) {
	var t = goog.dom.createDom("DIV", {className: "toast"});
	t.innerHTML = message;
	this.toasts += 1;
	this.toasts_div.appendChild(t);
	setTimeout(goog.bind(this.expire_toast, this, t), timeout);
    }

    expire_toast(t) {
	goog.dom.classlist.addRemove(t, "toast", "toasthidden");
	setTimeout(goog.bind(this.delete_toast, this, t), 600);
    }

    delete_toast(t) {
	this.toasts -= 1;
	this.dead_toasts.push(t);
	// We only actually delete the toast elements once no toasts
	// are visible, to prevent toasts from visibly moving around.
	if (this.toasts == 0) {
	    for (var i = 0; i < this.dead_toasts.length; ++i) {
		goog.dom.removeNode(this.dead_toasts[i]);
	    }
	    this.dead_toasts = [];
	}
    }
}

var waiter = null;
var submit_dialog = null;
var time_formatter = null;
var toast_manager = null;

function initPage() {
    time_formatter = new TimeFormatter();
    toast_manager = new ToastManager();

    waiter = new Waiter(new Dispatcher());
    waiter.start();

    // Only present on the puzzle pages.
    var a = goog.dom.getElement("submit");
    if (a) {
	submit_dialog = new SubmitDialog();
	a.onclick = function() { submit_dialog.show(); return false; };
    }

    // Only present on the map pages.
    var m = goog.dom.getElement("map");
    if (m) {
	for (var i = 0; i < icons.length; ++i) {
	    var url = icons[i][0];
	    var x = icons[i][1];
	    var y = icons[i][2];

	    var el = goog.dom.createDom("IMG", {"src": url});
	    el.style.left = "" + x + "px";
	    el.style.top = "" + y + "px";
	    m.appendChild(el);
	}
    }

    // Only present on the activity log page.
    var log = goog.dom.getElement("log");
    if (log) {
	for (var i = 0; i < log_entries.length; ++i) {
	    var t = log_entries[i][0];
	    var html = log_entries[i][1];

	    var span = goog.dom.createDom("SPAN");
	    span.innerHTML = time_formatter.format(t) + " &mdash; " + html;
	    var li = goog.dom.createDom("LI", null, span);
	    log.appendChild(li);
	}
    }
}

window.onload = initPage;

