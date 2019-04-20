goog.require('goog.dom');
goog.require('goog.dom.TagName');
goog.require('goog.events');
goog.require('goog.net.XhrIo');


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

function initPage() {
    //waiter = new Waiter();

    var a = goog.dom.getElement("submit");
    if (a) {
	a.onclick = showSubmit;
    }
}

window.onload = initPage;

function showSubmit() {
    alert("submit!");
    return false;
}
