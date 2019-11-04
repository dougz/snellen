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
    /** @param{function(string)} notify_fn */
    constructor(dispatcher, base_url, notify_fn) {
        /** @type{string} */
        this.base_url = base_url;

        this.notify_fn = notify_fn;

        /** @type{goog.net.XhrIo} */
        this.xhr = new goog.net.XhrIo();
        /** @type{number} */
        this.serial = received_serial;

        if (window.performance.navigation.type == 2) {
            var e = sessionStorage.getItem("serial");
            if (e) {
                e = parseInt(e, 10);
                if (e > this.serial) {
                    this.serial = e;
                }
            }
        }

        /** @type{number} */
        this.backoff = 250;
        /** @type(Object) */
        this.dispatcher = dispatcher;
        /** @type{boolean} */
        this.saw_502 = false;
    }

    waitcomplete() {
        if (this.xhr.getStatus() == 502) {
            this.saw_502 = true;
        }

        if (this.xhr.getStatus() == 401) {
            var text;
            if (this.saw_502) {
                text = "Server connection lost. Please reload to continue."
            } else {
                text = "You have been logged out. Please reload to continue."
            }
            this.notify_fn(text);
            return;
        }

        if (this.xhr.getStatus() != 200) {
            this.backoff = Math.min(10000, Math.floor(this.backoff*1.5));

            // // XXX cancel early for development
            // if (this.backoff > 1000) {
            //  console.log("aborting retries");
            //  return;
            // }

            setTimeout(goog.bind(this.xhr.send, this.xhr,
                                 this.base_url + "/" + wid + "/" + this.serial),
                       this.backoff);
            return;
        }

        this.backoff = 250;

        var msgs = /** @type{Array<Object>} */ (this.xhr.getResponseJson());
        for (var i = 0; i < msgs.length; ++i) {
            this.serial = /** @type{number} */ (msgs[i][0]);
            var msg = /** @type{Object} */ (msgs[i][1]);
            this.dispatcher.dispatch(msg);
        }

        sessionStorage.setItem("serial", this.serial.toString());

        setTimeout(goog.bind(this.xhr.send, this.xhr,
                             this.base_url + "/" + wid + "/" + this.serial),
                   Math.random() * 250);
    }

    start() {
        goog.events.listen(this.xhr, goog.net.EventType.COMPLETE,
                           goog.bind(this.waitcomplete, this));
        this.xhr.send(this.base_url + "/" + wid + "/" + this.serial);
    }
}

