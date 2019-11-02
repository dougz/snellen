class Common_TimeFormatter {
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

