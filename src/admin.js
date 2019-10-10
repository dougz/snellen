goog.require("goog.dom");
goog.require("goog.dom.classlist");
goog.require("goog.events");
goog.require("goog.events.KeyCodes");
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
            "update": this.update,
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
        if (admin2020.bigboard) {
            admin2020.bigboard.refresh_hintqueue();
        }
    }

    /** @param{Message} msg */
    update(msg) {
        if (msg.team_username) {
            if (admin2020.bigboard) {
                admin2020.bigboard.refresh_team(msg.team_username);
            }
            if (admin2020.team_page && team_username == msg.team_username) {
                admin2020.team_page.update();
            }
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
            var claimlink = goog.dom.createDom("A", {href: msg.claim, target: "_blank"}, "Claim");
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
        var now = (new Date()).getTime() / 1000.0;
        for (var i = 0; i < this.els.length; ++i) {
            var el = this.els[i];
            var since = el.getAttribute("data-since");
            if (since) {
                el.innerHTML = admin2020.time_formatter.duration(now-since);
            } else {
                var until = el.getAttribute("data-until");
                if (until) {
                    var d = until - now;
                    if (d < 0) d = 0;
                    el.innerHTML = admin2020.time_formatter.duration(d);
                }
            }
        }
    }
}

class A2020_UserRoles {
    constructor() {
        var cbs = document.querySelectorAll("table#user-roles input[type='checkbox']");
        for (var i = 0; i < cbs.length; ++i) {
            var cb = cbs[i];
            goog.events.listen(cb, goog.events.EventType.CHANGE,
                               goog.bind(this.alter_role, this));
        }
    }

    alter_role(e) {
        var n = e.target.id.search("::");
        var user = e.target.id.substring(0, n);
        var role = e.target.id.substring(n+2);

        goog.net.XhrIo.send("/admin/" + (e.target.checked ? "set" : "clear") + "_role/" + user + "/" + role,
                            function(e) {
                                var xhr = e.target;
                                if (xhr.getStatus() != 204) {
                                    alert("Updating " + user + " " + role + " failed: " + xhr.getResponseText());
                                }
                            });
    }
}

class A2020_Autocomplete {
    /** @param{Element} select */
    /** @param{Array<Array<string>>} data */
    constructor(select, data, invoke) {
        this.data = data;
        this.search = [];
        for (var i = 0; i < data.length; ++i) {
            this.search.push(data[i][1].toLowerCase());
        }

        this.select = select;
        for (var i = 0; i < select.childNodes.length; ++i) {
            var el = select.childNodes[i];
            if (el.className == "ac-select-input") {
                this.input = el;
            } else if (el.className == "ac-select-dropdown") {
                this.dropdown = el;
            }
        }
        this.highlight = -1;
        this.matches = [];

        this.invoke = invoke;

        goog.events.listen(this.input, goog.events.EventType.INPUT,
                           goog.bind(this.oninput, this));
        goog.events.listen(this.input, goog.events.EventType.KEYDOWN,
                           goog.bind(this.onkeypress, this));
    }

    oninput() {
        var value = this.input.value;

        this.highlight = -1;

        if (!value) {
            this.dropdown.style.display = "none";
            return;
        }
        value = value.toLowerCase();

        this.dropdown.innerHTML = "";
        this.dropdown.style.display = "inline-block";

        this.matches = [];
        var matches = 0;
        for (var i = 0; i < this.search.length; ++i) {
            var pos = this.search[i].indexOf(value);
            if (pos < 0) continue;
            ++matches;
            if (matches <= 5) {
                var m = this.data[i][1];
                var row = goog.dom.createDom(
                    "SPAN", "ac-row",
                    goog.dom.createTextNode(m.substring(0, pos)),
                    goog.dom.createDom("SPAN", "ac-match", m.substring(pos, pos+value.length)),
                    goog.dom.createTextNode(m.substring(pos+value.length)));
                row.setAttribute("data-target", this.data[i][0]);
                goog.events.listen(row, goog.events.EventType.CLICK,
                                   goog.bind(this.invoke_row, this, row));
                this.matches.push(row);
                this.dropdown.appendChild(row);
            }
        }
        if (matches > 5) {
            this.dropdown.appendChild(goog.dom.createDom("SPAN", "ac-overflow", "(" + (matches-5) + " more matches)"));
        }
        if (matches == 0) {
            this.dropdown.appendChild(goog.dom.createDom("SPAN", "ac-none", "No matches."));
        }
        if (matches == 1) this.move_highlight(1);
    }

    onkeypress(e) {
        if (e.keyCode == goog.events.KeyCodes.DOWN) {
            this.move_highlight(1);
            e.preventDefault();
        } else if (e.keyCode == goog.events.KeyCodes.UP) {
            this.move_highlight(-1);
            e.preventDefault();
        } else if (e.keyCode == goog.events.KeyCodes.ENTER) {
            if (this.highlight >= 0) {
                this.invoke_row(this.matches[this.highlight]);
            }
            e.preventDefault();
        }
    }

    move_highlight(d) {
        if (this.highlight + d < -1 || this.highlight + d >= this.matches.length) return;

        if (this.highlight >= 0) {
            goog.dom.classlist.remove(this.matches[this.highlight], "ac-selected");
        }
        this.highlight += d;
        if (this.highlight >= 0) {
            goog.dom.classlist.add(this.matches[this.highlight], "ac-selected");
        }
    }

    invoke_row(row) {
        var target = row.getAttribute("data-target");
        this.invoke(target);
    }

}

class A2020_TeamPage {
    constructor() {
        /** @type{Element} */
        this.tpopencount = goog.dom.getElement("tpopencount");
        /** @type{Element} */
        this.tpopenlist = goog.dom.getElement("tpopenlist");
        /** @type{Element} */
        this.tpfastpass = goog.dom.getElement("tpfastpass");
        /** @type{Element} */
        this.tplog = goog.dom.getElement("tplog");

        var el = goog.dom.getElement("bestowfastpass");
        goog.events.listen(el, goog.events.EventType.CLICK, function() {
            goog.net.XhrIo.send("/admin/bestowfastpass/" + team_username, function(e) {
                var code = e.target.getStatus();
                if (code != 204) {
                    alert(e.target.getResponseText());
                }
            });
        });

        this.update();
    }

    update() {
        goog.net.XhrIo.send("/admin/js/team/" + team_username, goog.bind(function(e) {
            var code = e.target.getStatus();
            if (code != 200) {
                alert(e.target.getResponseText());
            }
            this.build(e.target.getResponseJson());
        }, this), "GET");
    }

    /** param{TeamPageData} data */
    build(data) {
        console.log(data);
        this.tpopencount.innerHTML = "" + data.open_puzzles.length;

        var i, j;

        var el = this.tpopenlist;
        el.innerHTML = "";
        for (i = 0; i < data.open_puzzles.length; ++i) {
            var op = data.open_puzzles[i];
            if (i > 0) {
                el.appendChild(goog.dom.createDom("BR"));
            }
            el.appendChild(goog.dom.createDom(
                "A", {href: "/admin/team/" + team_username + "/puzzle/" + op.shortname},
                op.title));
            el.appendChild(goog.dom.createTextNode(" ("));
            var sp = goog.dom.createDom("SPAN", "counter");
            sp.setAttribute("data-since", op.open_time);
            el.appendChild(sp);
            el.appendChild(goog.dom.createTextNode(")"));
            if (!op.answers_found) continue;
            el.appendChild(goog.dom.createTextNode(" \u2014 "));
            for (j = 0; j < op.answers_found.length; ++j) {
                if (j > 0) {
                    el.appendChild(goog.dom.createTextNode(", "));
                }
                el.appendChild(goog.dom.createDom("SPAN", "answer", op.answers_found[j]));
            }
        }

        el = this.tpfastpass;
        el.innerHTML = "";
        if (data.fastpasses) {
            for (i = 0; i < data.fastpasses.length; ++i) {
                if (i > 0) {
                    el.appendChild(goog.dom.createTextNode(", "));
                }
                var sp = goog.dom.createDom("SPAN", "counter");
                sp.setAttribute("data-until", data.fastpasses[i]);
                el.appendChild(sp);
            }
        }

        el = this.tplog;
        el.innerHTML = "";
        for (i = 0; i < data.log.length; ++i) {
            var e = data.log[i];
            var td = goog.dom.createDom("TD");
            for (j = 0; j < e.htmls.length; ++j) {
                if (j > 0) td.appendChild(goog.dom.createDom("BR"));
                var sp = goog.dom.createDom("SPAN");
                sp.innerHTML = e.htmls[j];
                td.appendChild(sp);
            }

            var tr = goog.dom.createDom("TR",
                                        null,
                                        goog.dom.createDom("TH", null, admin2020.time_formatter.format(e.when)),
                                        td);
            el.appendChild(tr);
        }


        admin2020.counter.reread();
    }
}

class A2020_BigBoard {
    constructor() {
        /** @type{Element} */
        this.hintqueue = goog.dom.getElement("bbhintqueue");
        this.refresh_hintqueue();

        this.team_data = null;
        this.team_els = [];

        /** @type{Element} */
        this.teamdiv = goog.dom.getElement("bbteams");

        goog.net.XhrIo.send("/admin/bb/team", goog.bind(function(e) {
            var code = e.target.getStatus();
            if (code != 200) {
                alert(e.target.getResponseText());
            }
            this.update_all_teams(e.target.getResponseJson());
        }, this), "GET");
    }

    update_all_teams(data) {
        this.team_data = data;

        for (var i = 0; i < team_list.length; ++i) {
            var username = team_list[i][0];
            var d = this.team_data[username];

            var score = goog.dom.createDom("DIV", "bb-score", "" + d.score);
            var name = goog.dom.createDom("DIV", "bb-name", team_list[i][1]);
            var svg = goog.dom.createDom("DIV", "bb-svg");
            svg.innerHTML = d.svg;

            var el = goog.dom.createDom("DIV", "bb-row", score, name, svg);
            el.setAttribute("data-username", username);

            this.team_data[username]["el"] = el;
            this.team_els.push(el);
        }

        this.reorder_teams();
    }

    refresh_team(username) {
        // Can't refresh until we have the initial data.
        if (this.team_data === null) return;

        goog.net.XhrIo.send("/admin/bb/team/" + username, goog.bind(function(e) {
            var code = e.target.getStatus();
            if (code != 200) {
                alert(e.target.getResponseText());
            }
            this.update_one_team(username, e.target.getResponseJson());
        }, this), "GET");
    }

    update_one_team(username, data) {
        console.log(data)

        var el = this.team_data[username]["el"];
        this.team_data[username] = data;
        this.team_data[username]["el"] = el;

        var score = el.firstChild;
        score.innerHTML = "" + data.score;

        var svg = score.nextSibling.nextSibling;
        svg.innerHTML = data.svg;

        this.reorder_teams();
    }

    reorder_teams() {
        this.team_els.sort(goog.bind(function(a_el, b_el) {
            var a = this.team_data[a_el.getAttribute("data-username")];
            var b = this.team_data[b_el.getAttribute("data-username")];

            // Decreasing order by score...
            var d = a.score - b.score;
            if (d != 0) return -d;

            // ...then increasing order of last score change time...
            d = a.score_change - b.score_change;
            if (d != 0) return d;

            // ...then team name.
            if (a.name < b.name) {
                return -1;
            } else if (a.name > b.name) {
                return 1;
            } else {
                return 0;
            }
        }, this));
        this.teamdiv.innerHTML = "";
        for (var i = 0; i < this.team_els.length; ++i) {
            this.teamdiv.appendChild(this.team_els[i]);
        }
    }

    refresh_hintqueue() {
        goog.net.XhrIo.send("/admin/bb/hintqueue", goog.bind(function(e) {
            var code = e.target.getStatus();
            if (code != 200) {
                alert(e.target.getResponseText());
            }
            this.update_hintqueue(/** @type{BBHintQueue} */ (e.target.getResponseJson()));
        }, this), "GET");
    }

    update_hintqueue(data) {
        if (!data) return;
        this.hintqueue.innerHTML = "" + data.size + " (" + (data.size - data.claimed) + ")";
    }
}

var admin2020 = {
    waiter: null,
    counter: null,
    hinthistory: null,
    hintqueue: null,
    time_formatter: null,
    serializer: null,
    puzzle_select: null,
    team_select: null,
    user_roles: null,
    bigboard: null,
    team_page: null,
}

window.onload = function() {
    admin2020.serializer = new goog.json.Serializer();
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

    var el;

    el = goog.dom.getElement("hinttimechange");
    if (el) {
        goog.events.listen(el, goog.events.EventType.CLICK, function() {
            goog.dom.getElement("hinttimechange").style.display = "none";
            goog.dom.getElement("hinttimechangeentry").style.display = "inline";
            goog.events.listen(goog.dom.getElement("newhinttimesubmit"), goog.events.EventType.CLICK, function() {
                var text = goog.dom.getElement("newhinttime").value;
                console.log("submitting [" + text + "]");
                goog.net.XhrIo.send("/admin/hinttimechange", function(e) {
                    var code = e.target.getStatus();
                    if (code == 204) {
                        location.reload();
                    } else {
                        alert(e.target.getResponseText());
                    }
                }, "POST", admin2020.serializer.serialize({"puzzle_id": puzzle_id, "hint_time": text}));
            });
        });
    }

    el = goog.dom.getElement("puzzleselect");
    if (el) {
        admin2020.puzzle_select = new A2020_Autocomplete(
            el, puzzle_list,
            function(shortname) {
                if (team_username) {
                    window.location.href = "/admin/team/" + team_username + "/puzzle/" + shortname;
                } else {
                    window.location.href = "/admin/puzzle/" + shortname;
                }
            });
    }

    el = goog.dom.getElement("teamselect");
    if (el) {
        admin2020.team_select = new A2020_Autocomplete(
            el, team_list,
            function(username) {
                if (puzzle_id) {
                    window.location.href = "/admin/team/" + username + "/puzzle/" + puzzle_id;
                } else {
                    window.location.href = "/admin/team/" + username;
                }
            });
    }

    if (goog.dom.getElement("user-roles")) {
        admin2020.user_roles = new A2020_UserRoles()
    }

    if (goog.dom.getElement("bbhintqueue")) {
        admin2020.bigboard = new A2020_BigBoard();
    }

    if (team_username && !puzzle_id) {
        admin2020.team_page = new A2020_TeamPage();
    }
}

