goog.require("goog.dom");
goog.require("goog.dom.TagName");
goog.require("goog.events");
goog.require("goog.net.XhrIo");
goog.require("goog.ui.ModalPopup");
goog.require("goog.ui.Dialog");
goog.require("goog.json.Serializer");

var TagName = goog.dom.TagName;

/** @constructor */
function Waiter() {
    this.xhr = new goog.net.XhrIo();
    this.other_xhr = new goog.net.XhrIo();
    this.count = 0;
    this.backoff = 100;
    this.waitcomplete = function() {
        if (this.xhr.getStatus() == 401) {
            alert(this.xhr.getResponseText());
            return;
        }

        this.count++;

        if (this.xhr.getStatus() != 200) {
            this.backoff = Math.min(10000, Math.floor(this.backoff*1.5));
            setTimeout(goog.bind(this.xhr.send, this.xhr, "/read/" + this.count),
                       this.backoff);
            return;
        }

        this.backoff = 100;

	var obj = this.xhr.getResponseText();
	var e = goog.dom.getElement("response");
	e.innerHTML = obj;

        var temp = this.xhr;
        this.xhr = this.other_xhr;
        this.other_xhr = temp;
        this.xhr.send("/read/" + this.count);
    };
    goog.events.listen(this.xhr, goog.net.EventType.COMPLETE, this.waitcomplete, false, this);
    goog.events.listen(this.other_xhr, goog.net.EventType.COMPLETE, this.waitcomplete, false, this);
    this.xhr.send("/read/" + this.count);
}


var waiter = null;

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
    }

    build() {
	this.serializer = new goog.json.Serializer();

	this.dialog = new goog.ui.ModalPopup();
	this.dialog.render();

	var content =  this.dialog.getContentElement();

	var title = goog.dom.createDom(TagName.DIV, {"class": "submit"}, "hello, world");
	content.appendChild(title);

	this.input = goog.dom.createDom(TagName.INPUT, {"name": "answer"}, "");
	content.appendChild(this.input);

	var b = goog.dom.createDom(TagName.BUTTON, null, "Submit");
	goog.events.listen(b, goog.events.EventType.CLICK, goog.bind(this.submit, this));
	content.appendChild(b);

	b = goog.dom.createDom(TagName.BUTTON, null, "Close");
	content.appendChild(b);
	goog.events.listen(b, goog.events.EventType.CLICK, goog.bind(this.close, this));

	this.built = true;
    }

    submit() {
	var answer = this.input.value;
	console.log("submitting [" + answer + "] for [" + puzzle_id + "]");
	goog.net.XhrIo.send("/submit", function(e) {
	    var code = e.target.getStatus();
	    if (code != 204) {
		alert(e.target.getResponseText());
	    }
	}, "POST", this.serializer.serialize({"puzzle_id": puzzle_id, "answer": answer}));
    }

    show() {
	if (!this.built) this.build();
	this.dialog.setVisible(true);
	return false;
    }

    close() {
	this.dialog.setVisible(false);
    }
}

var submit_dialog = new SubmitDialog();

function initPage() {
    //waiter = new Waiter();

    var a = goog.dom.getElement("submit");
    if (a) {
	a.onclick = function() { submit_dialog.show(); return false; };
    }
}

window.onload = initPage;

