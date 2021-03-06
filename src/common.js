goog.require("goog.i18n.DateTimeFormat");

class Common_TimeFormatter {
    constructor() {
        this.formatter = new goog.i18n.DateTimeFormat("EEE h:mm:ss aa");
    }

    /** @param{number} t */
    format(t) {
        var d = new Date(t * 1000);
        var txt = this.formatter.format(d);
        var l = txt.length;
        return txt.substr(0, l-2) + txt.substr(l-2, 2).toLowerCase();
    }

    /** @param{number} s */
    duration(s) {
        var hr = Math.trunc(s/3600);
        s -= hr*3600;
        var min = Math.trunc(s/60);
        var sec = Math.trunc(s%60);
        if (hr > 0) {
            return "" + hr + ":" + (""+min).padStart(2, "0") + ":" + (""+sec).padStart(2, "0");
        } else {
            return "" + min + ":" + (""+sec).padStart(2, "0");
        }
    }
}

class Common_Counter {
    /** @param{Common_TimeFormatter} time_formatter */
    constructor(time_formatter) {
        this.time_formatter = time_formatter;
        this.timer = null;
        this.els = [];
        this.reread();
    }

    reread() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
        this.els = document.querySelectorAll(".counter");
        if (this.els.length > 0) {
            this.timer = setInterval(goog.bind(this.update, this), 1000);
        }
        this.update();
    }

    update() {
        var dirty = false;
        var now = (new Date()).getTime() / 1000.0;
        for (var i = 0; i < this.els.length; ++i) {
            var el = this.els[i];

            // Time elapsed since a point, as hh:mm:ss.
            var since = el.getAttribute("data-since");
            if (since) {
                el.innerHTML = this.time_formatter.duration(now-since);
                continue;
            }

            // Time remaining until a point, as hh:mm:ss.
            var until = el.getAttribute("data-until");
            if (until) {
                var d = until - now;
                if (d < 0) d = 0;
                el.innerHTML = this.time_formatter.duration(d);
                continue;
            }

            // At time point, delete the element. ("NEW" tags in land maps.)
            var expires = el.getAttribute("data-expires");
            if (expires) {
                if (now > parseFloat(expires)) {
                    el.parentNode.removeChild(el);
                    dirty = true;
                }
                continue;
            }

            // Time remaining until a point, in seconds.  ("Mark done" in task queue.)
            until = el.getAttribute("data-until-secs");
            if (until) {
                var d = until - now;
                if (d < 0) d = 0;
                el.innerHTML = "" + Math.round(d);
                continue;
            }
        }
        if (dirty) this.reread();
    }
}

class Common_Waiter {
    /** @param{Object} dispatcher */
    /** @param{string} base_url */
    /** @param{number} start_serial */
    /** @param{?Storage} storage */
    /** @param{?function(string)} notify_fn */
    constructor(dispatcher, base_url, start_serial, storage, notify_fn) {
        this.dispatcher = dispatcher;
        this.notify_fn = notify_fn;
        this.storage = storage;
        this.serial = start_serial;

        var protocol = null;
        if (window.performance && window.performance.timing.nextHopProtocol) {
            protocol = window.performance.timing.nextHopProtocol;
        } else if (window.performance && window.performance.getEntries) {
            protocol = window.performance.getEntries()[0].nextHopProtocol;
        }

        // For HTTP/2, we can wait on the same connection we used to
        // load the page.  For HTTP/1.1, we use a sharded domain to
        // get around browser per-host connection limit.
        if (goog.DEBUG || protocol == "h2") {
            console.log("waiter uses protocol", protocol, ": main domain");
            this.base_url = base_url + "/" + wid;
        } else {
            console.log("waiter uses protocol", protocol, ": sharded domain");
            this.base_url = location.protocol + "//w" + wid + "." + location.hostname + base_url + "/" + wid;
        }

        /** @type{goog.net.XhrIo} */
        this.xhr = new goog.net.XhrIo();
        this.xhr.setWithCredentials(true);

        if (storage && window.performance.navigation.type == 2) {
            var e = storage.getItem("serial");
            if (e) {
                e = parseInt(e, 10);
                if (e > this.serial) {
                    this.serial = e;
                }
            }
        }

        /** @type{number} */
        this.retry_backoff = 250;
        /** @type{boolean} */
        this.saw_error = false;

        /** @type{number} */
        this.respond_deadline = 90;

        goog.events.listen(this.xhr, goog.net.EventType.COMPLETE,
                           goog.bind(this.waitcomplete, this));
    }

    start() {
        this.send();
    }

    waitcomplete(e) {
        if (goog.DEBUG) {
            console.log("wait response is", e.target.getStatus());
        }
        if (e.target.getStatus() >= 500) {
            this.saw_error = true;
        }

        if (e.target.getStatus() == 401) {
            var text;
            if (this.saw_error) {
                text = "Server connection lost. Please reload to continue."
            } else {
                text = "You have been logged out. Please reload to continue."
            }
            this.notify_fn(text);
            return;
        }

        if (e.target.getStatus() != 200) {
            this.retry_backoff = Math.min(10000, Math.floor(
                this.retry_backoff*(1.4 + Math.random() * 0.2)));
            setTimeout(goog.bind(this.send, this), this.retry_backoff);
            return;
        }
        this.retry_backoff = 250;

        var msgs = /** @type{Array<Object>} */ (e.target.getResponseJson());
        if (msgs.length > 0) {
            if (this.dispatcher.pre_dispatch) this.dispatcher.pre_dispatch();
            for (var i = 0; i < msgs.length; ++i) {
                this.serial = /** @type{number} */ (msgs[i][0]);
                var msg = /** @type{Object} */ (msgs[i][1]);
                if (goog.DEBUG) {
                    console.log("dispatching", this.serial, msg);
                }
                this.dispatcher.dispatch(msg);
            }
            if (this.dispatcher.post_dispatch) this.dispatcher.post_dispatch();
        }

        if (msgs.length == 0) {
            this.respond_deadline = Math.round(this.respond_deadline * 1.5);
            if (this.respond_deadline > 300) {
                this.respond_deadline = 300;
            }
        } else {
            this.respond_deadline = 90;
        }

        if (this.storage) {
            this.storage.setItem("serial", this.serial.toString());
        }

        setTimeout(goog.bind(this.send, this), Math.random() * 250);
    }

    send() {
        this.xhr.send(this.base_url + "/" + this.serial +
                      "/" + this.respond_deadline, "GET", null);
    }
}

function Common_expect_204(e) {
    var code = e.target.getStatus();
    if (code != 204) {
        if (goog.DEBUG) {
            alert(e.target.getResponseText());
        }
    }
}

function Common_invoke_with_json(obj, target) {
    var cb = goog.bind(target, obj);
    return function(e) {
        var code = e.target.getStatus();
        if (code == 200) {
            cb(e.target.getResponseJson());
        } else if (code == 204) {
            cb();
        } else {
            if (goog.DEBUG) {
                alert(e.target.getResponseText());
            }
        }
    }
}

function Common_invoke_with_json_arg(obj, target, arg) {
    var cb = goog.bind(target, obj, arg);
    return function(e) {
        var code = e.target.getStatus();
        if (code == 200) {
            cb(e.target.getResponseJson());
        } else if (code == 204) {
            cb();
        } else {
            if (goog.DEBUG) {
                alert(e.target.getResponseText());
            }
        }
    }
}

class Common_enabler {
    /** param{string} enable_id */
    /** param{string} action_id */
    /** param{function()} action */

    constructor(enable_id, action_id, action) {
        /** type{Element} */
        this.enable_el = goog.dom.getElement(enable_id);
        /** type{Element} */
        this.action_el = goog.dom.getElement(action_id);

        if (!this.enable_el || !this.action_el) return;

        this.action = action;

        this.enable_el.disabled = false;
        this.action_el.disabled = true;

        goog.events.listen(this.enable_el, goog.events.EventType.CLICK,
                           goog.bind(this.do_enable, this));
        goog.events.listen(this.action_el, goog.events.EventType.CLICK,
                           goog.bind(this.do_action, this));
    }

    do_enable() {
        this.action_el.disabled = !this.action_el.disabled;
    }

    do_action() {
        this.action_el.blur();
        this.action_el.disabled = true;
        this.action();
    }
}




