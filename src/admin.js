goog.require("goog.dom");
goog.require("goog.events");
goog.require("goog.net.XhrIo");
goog.require("goog.json.Serializer");
goog.require("goog.i18n.DateTimeFormat");

class A2020_Waiter {
    constructor(dispatcher) {
        /** @type{goog.net.XhrIo} */
        this.xhr = new goog.net.XhrIo();
        /** @type{number} */
        this.serial = received_serial;
        /** @type{number} */
        this.backoff = 250;

        /** @type(A2020_Dispatcher) */
        this.dispatcher = dispatcher;
    }

    waitcomplete() {
        if (this.xhr.getStatus() == 401) {
            alert("Server connection lost; please reload.");
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
                                 "/wait/" + waiter_id + "/" + this.serial),
                       this.backoff);
            return;
        }

        this.backoff = 250;

        var msgs = /** @type{Array<Object>} */ (this.xhr.getResponseJson());
        for (var i = 0; i < msgs.length; ++i) {
            this.serial = /** @type{number} */ (msgs[i][0]);
            var msg = /** @type{Message} */ (msgs[i][1]);
            this.dispatcher.dispatch(msg);
        }

        setTimeout(goog.bind(this.xhr.send, this.xhr,
                             "/wait/" + waiter_id + "/" + this.serial),
                   Math.random() * 250);
    }

    start() {
        goog.events.listen(this.xhr, goog.net.EventType.COMPLETE,
                           goog.bind(this.waitcomplete, this));
        this.xhr.send("/wait/" + waiter_id + "/" + this.serial);
    }
}

class A2020_Dispatcher {
    constructor() {
        this.methods = {
            "hint_history": this.hint_history,
            "hint_queue": this.hint_queue,
        }
    }

    /** @param{Message} msg */
    dispatch(msg) {
        console.log(msg);
        this.methods[msg.method](msg);
    }

    /** @param{Message} msg */
    hint_history(msg) {
        if (admin2020.hinthistory &&
            msg.puzzle_id == puzzle_id &&
            msg.team_username == team_username) {
            admin2020.hinthistory.update_history();
        }
    }

    /** @param{Message} msg */
    hint_queue(msg) {
        if (admin2020.hintqueue) {
            admin2020.hintqueue.update_queue();
        }
    }
}

class A2020_HintHistory {
    constructor() {
        /** @type{Object|null} */
        this.serializer = new goog.json.Serializer();

        /** @type{Element} */
        this.textarea = goog.dom.getElement("replytext");
        this.textarea.focus();

        /** @type{Element} */
        this.history = goog.dom.getElement("hinthistory");

        /** @type{Element} */
        this.claim = goog.dom.getElement("hintclaim");

        /** @type{Element} */
        this.claimlink = goog.dom.getElement("claimlink");
        /** @type{Element} */
        this.unclaimlink = goog.dom.getElement("unclaimlink");

        var b = goog.dom.getElement("hintreply");
        goog.events.listen(b, goog.events.EventType.CLICK, goog.bind(this.submit, this));

        this.update_history();
    }

    submit() {
        var text = this.textarea.value;
        if (text == "") return;
        this.textarea.value = "";
        goog.net.XhrIo.send("/admin/hintreply", function(e) {
            var code = e.target.getStatus();
            if (code != 204) {
                alert(e.target.getResponseText());
            }
        }, "POST", this.serializer.serialize({"team_username": team_username, "puzzle_id": puzzle_id, "text": text}));
    }

    update_history() {
        goog.net.XhrIo.send("/admin/hinthistory/" + team_username + "/" + puzzle_id, goog.bind(function(e) {
            var code = e.target.getStatus();
            if (code == 200) {
                var response = /** @type{HintHistory} */ (e.target.getResponseJson());
                console.log(response);
                this.render_history(response);
            }
        }, this));
    }

    /** @param{HintHistory} response */
    render_history(response) {
        if (response.claim) {
            this.claim.style.display = "inline";
            this.claim.innerHTML = "Claimed by " + response.claim;
            this.claimlink.style.display = "none";
            this.unclaimlink.style.display = "inline-block";
        } else {
            this.claim.style.display = "none";
            this.claimlink.style.display = "inline-block";
            this.unclaimlink.style.display = "none";
        }

        if (response.history.length == 0) {
            this.history.innerHTML = "Team has not requested any hints.";
            return;
        }
        this.history.innerHTML = "";
        var dl = goog.dom.createDom("DL");
        for (var i = 0; i < response.history.length; ++i) {
            var msg = response.history[i];
            var dt = goog.dom.createDom(
                "DT", null,
                "At " + admin2020.time_formatter.format(msg.when) + ", " + msg.sender + " wrote:");
            var dd = goog.dom.createDom("DD", null);
            dd.innerHTML = msg.text;
            dl.appendChild(dt);
            dl.appendChild(dd);
        }
        this.history.appendChild(dl);
    }
}

class A2020_HintQueue {
    constructor() {
        /** @type{Element|null} */
        this.queue = goog.dom.getElement("hintqueue");
        this.tbody = goog.dom.getElement("hintqueuedata");
        this.update_queue();
    }

    update_queue() {
        goog.net.XhrIo.send("/admin/hintqueuedata", goog.bind(function(e) {
            var code = e.target.getStatus();
            if (code == 200) {
                var response = /** @type{HintQueue} */ (e.target.getResponseJson());
                console.log(response);
                this.render_queue(response);
            }
        }, this));
    }

    /** @param{HintQueue} response */
    render_queue(response) {
        if (response.queue.length == 0) {
            this.tbody.innerHTML = "<tr><td colspan=6 style=\"padding: 20px;\">No hint requests are waiting.</td></tr>"
            return;
        }
        this.tbody.innerHTML = "";
        var now = (new Date()).getTime() / 1000.0;
        for (var i = 0; i < response.queue.length; ++i) {
            var msg = response.queue[i];
            var td = goog.dom.createDom("TD", "hqtime counter", admin2020.time_formatter.duration(now-msg.when));
            td.setAttribute("data-since", msg.when);
            var claimlink = goog.dom.createDom("A", {href: msg.claim}, "Claim");
            if (msg.claimant) {
                claimlink.style.visibility = "hidden";
            }
            var tr = goog.dom.createDom(
                "TR", null,
                td,
                goog.dom.createDom("TD", {className: "hqteam"}, msg.team),
                goog.dom.createDom("TD", {className: "hqpuzzle"}, msg.puzzle),
                goog.dom.createDom("TD", {className: "hqview"},
                                   goog.dom.createDom("A", {href: msg.target, target: "_blank"},
                                                      "View")),
                goog.dom.createDom("TD", {className: "hqclaim"}, claimlink),
                goog.dom.createDom("TD", {className: "hqclaimant"}, msg.claimant));
            this.tbody.appendChild(tr);
        }
        admin2020.counter.reread();
    }
}

class A2020_TimeFormatter {
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

class A2020_Counter {
    constructor() {
        this.timer = setInterval(goog.bind(this.update, this), 1000);
        this.els = [];
        this.reread();

    }

    reread() {
        this.els = document.querySelectorAll(".counter");
    }

    update() {
        var now = (new Date()).getTime() / 1000.0;
        for (var i = 0; i < this.els.length; ++i) {
            var el = this.els[i];
            var since = el.getAttribute("data-since");
            if (since) {
                el.innerHTML = admin2020.time_formatter.duration(now-since);
            } else {
                var until = el.getAttribute("data-until");
                if (until) {
                    el.innerHTML = admin2020.time_formatter.duration(until-now);
                }
            }
        }
    }
}




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

var admin2020 = {
    waiter: null,
    counter: null,
    hinthistory: null,
    hintqueue: null,
    time_formatter: null,
}

window.onload = function() {
    admin2020.waiter = new A2020_Waiter(new A2020_Dispatcher());
    admin2020.waiter.start();

    admin2020.time_formatter = new A2020_TimeFormatter();

    admin2020.counter = new A2020_Counter();

    if (goog.dom.getElement("hinthistory")) {
        admin2020.hinthistory = new A2020_HintHistory();
    }
    if (goog.dom.getElement("hintqueue")) {
        admin2020.hintqueue = new A2020_HintQueue();
    }
}
