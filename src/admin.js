goog.require("goog.dom");
goog.require("goog.dom.classlist");
goog.require("goog.events");
goog.require("goog.events.KeyCodes");
goog.require("goog.net.XhrIo");
goog.require("goog.json.Serializer");

class A2020_Dispatcher {
    constructor() {
        /** @type{boolean} */
        this.dirty_lists = false;

        this.methods = {
            "task_queue": goog.bind(this.task_queue, this),
            "update": goog.bind(this.update, this),
        }
    }

    pre_dispatch() {
        this.dirty_lists = false;
    }

    post_dispatch() {
        if (this.dirty_lists) {
            if (admin2020.puzzle_list_page) admin2020.puzzle_list_page.update();
            if (admin2020.team_list_page) admin2020.team_list_page.update();
        }
    }

    /** @param{Message} msg */
    dispatch(msg) {
        this.methods[msg.method](msg);
    }

    /** @param{Message} msg */
    task_queue(msg) {
        if (admin2020.taskqueue) {
            admin2020.taskqueue.update_queue();
        }
        if (admin2020.bigboard) {
            admin2020.bigboard.refresh_taskqueue();
        }
    }

    /** @param{Message} msg */
    update(msg) {
        if (msg.team_username) {
            if (admin2020.bigboard) {
                admin2020.bigboard.refresh_team(msg.team_username);
            }
            if (team_username == msg.team_username) {
                if (admin2020.team_page) admin2020.team_page.update();
                if (admin2020.team_puzzle_page && puzzle_id == msg.puzzle_id) {
                    admin2020.team_puzzle_page.update();
                }
            }
        }
        if (msg.puzzle_id && puzzle_id == msg.puzzle_id && admin2020.puzzle_page) {
            admin2020.puzzle_page.update();
        }
        if (admin2020.errata_page) {
            admin2020.errata_page.update();
        }
        this.dirty_lists = true;
    }
}

/** @param{Action} data */
/** @param{function(Object)} callback */
function A2020_DoAction(data, callback) {
    goog.net.XhrIo.send("/admin/action", callback, "POST",
                        admin2020.serializer.serialize(data));
}

class A2020_TeamListPage {
    constructor() {
        twemoji.parse(goog.dom.getElement("admincontent"));
    }
}

class A2020_TeamPuzzlePage {
    constructor() {
        /** @type{Element} */
        this.textarea = goog.dom.getElement("tppreplytext");

        /** @type{Element} */
        this.history = goog.dom.getElement("tpphinthistory");
        /** @type{Element} */
        this.replycontainer = goog.dom.getElement("tppreplycontainer");

        /** @type{Element} */
        this.claim = goog.dom.getElement("tpphintclaim");

        /** @type{Element} */
        this.claimlink = goog.dom.getElement("tppclaimlink");
        /** @type{Element} */
        this.unclaimlink = goog.dom.getElement("tppunclaimlink");

        /** @type{Element} */
        this.tppstate = goog.dom.getElement("tppstate");
        /** @type{Element} */
        this.tppopen = goog.dom.getElement("tppopen");
        /** @type{Element} */
        this.tppsolve = goog.dom.getElement("tppsolve");

        /** @type{Element} */
        this.tppsubmithead = goog.dom.getElement("tppsubmithead");
        /** @type{Element} */
        this.tppsubmitbody = goog.dom.getElement("tppsubmitbody");

        goog.events.listen(goog.dom.getElement("tpphintreply"),
                           goog.events.EventType.CLICK, goog.bind(this.submit, this, true));
        goog.events.listen(goog.dom.getElement("tpphintnoreply"),
                           goog.events.EventType.CLICK, goog.bind(this.submit, this, false));

        goog.events.listen(this.claimlink, goog.events.EventType.CLICK,
                           goog.bind(this.do_claim, this, "claim"));
        goog.events.listen(this.unclaimlink, goog.events.EventType.CLICK,
                           goog.bind(this.do_claim, this, "unclaim"));

        goog.events.listen(goog.dom.getElement("tppreset"),
                           goog.events.EventType.CLICK, goog.bind(this.reset_spam, this));

        this.update();
    }

    reset_spam() {
        A2020_DoAction({action: "reset_spam",
                        team_username: team_username,
                        puzzle_id: puzzle_id}, Common_expect_204);
    }

    do_claim(which) {
        A2020_DoAction({action: "update_claim",
                        which: which,
                        key: "h-" + team_username + "-" + puzzle_id}, Common_expect_204);
    }

    submit(has_reply) {
        var d = {"action": "hint_reply", "team_username": team_username, "puzzle_id": puzzle_id};
        if (has_reply) {
            var text = this.textarea.value;
            if (text == "") return;
            this.textarea.value = "";
            d["text"] = text;
        }
        A2020_DoAction(d, Common_expect_204);
    }

    update() {
        goog.net.XhrIo.send(
            "/admin/js/teampuzzle/" + team_username + "/" + puzzle_id,
            Common_invoke_with_json(this, this.build));
    }

    /** @param{TeamPuzzlePageData} data */
    build(data) {
        if (goog.DEBUG) {
            console.log(data);
        }
        goog.dom.classlist.set(this.tppstate, "puzzlestate-" + data.state);
        this.tppstate.innerHTML = data.state;

        if (data.open_time) {
            this.tppopen.innerHTML = admin2020.time_formatter.format(data.open_time);
            if (data.state == "open") {
                this.tppopen.appendChild(goog.dom.createTextNode(" ("));
                var sp = goog.dom.createDom("SPAN", "counter");
                sp.setAttribute("data-since", data.open_time);
                this.tppopen.appendChild(sp);
                this.tppopen.appendChild(goog.dom.createTextNode(")"));
            }
        } else {
            this.tppopen.innerHTML = "\u2014";
        }
        if (data.solve_time) {
            this.tppsolve.innerHTML = admin2020.time_formatter.format(data.solve_time) +
                " (" + admin2020.time_formatter.duration(data.solve_time - data.open_time) + ")";
        } else {
            this.tppsolve.innerHTML = "\u2014";
        }

        if (data.hints_open) {
            this.replycontainer.style.display = "initial";

            if (data.claim) {
                this.claim.style.display = "inline";
                this.claim.innerHTML = "Claimed by " + data.claim;
                this.claimlink.style.display = "none";
                this.unclaimlink.style.display = "inline-block";
            } else {
                this.claim.style.display = "none";
                this.claimlink.style.display = "inline-block";
                this.unclaimlink.style.display = "none";
            }

            if (data.history.length == 0) {
                this.history.innerHTML = "<i>Team has not requested any hints.</i>";
            } else {
                this.history.innerHTML = "";
                var dl = goog.dom.createDom("DL");
                for (var i = 0; i < data.history.length; ++i) {
                    var msg = data.history[i];
                    var dt = goog.dom.createDom(
                        "DT", null,
                        "At " + admin2020.time_formatter.format(msg.when) + ", " + msg.sender + " wrote:");
                    var dd = goog.dom.createDom("DD", msg.special ? "special" : null);
                    if (msg.special) {
                        if (msg.special == "cancel") {
                            dd.innerHTML = "(request canceled by team)";
                        } else if (msg.special == "solved") {
                            dd.innerHTML = "(puzzle was solved)";
                        } else if (msg.special == "ack") {
                            dd.innerHTML = "(no reply needed)";
                        }
                    } else {
                        dd.innerHTML = msg.text;
                    }
                    dl.appendChild(dt);
                    dl.appendChild(dd);
                }
                this.history.appendChild(dl);
            }
        } else {
            this.history.innerHTML = "<i>Hints are not available for this team and puzzle.</i>";
            this.replycontainer.style.display = "none";
        }

        var tr = null;
        this.tppsubmitbody.innerHTML = "";
        if (data.submits.length == 0) {
            this.tppsubmitbody.appendChild(
                goog.dom.createDom("TD", {className: "submit-empty", colSpan: 3}, "No submissions yet."));
            this.tppsubmithead.style.display = "none";
        } else {
            this.tppsubmithead.style.display = "table-header-group";
        }
        for (var i = 0; i < data.submits.length; ++i) {
            var sub = data.submits[i];
            var el = null;
            if (sub.state == "pending") {
                el = goog.dom.createDom("SPAN", {className: "counter submit-timer"});
                el.setAttribute("data-until", sub.check_time)
            }

            var time_el = null;
            if (sub.state == "pending") {
                time_el = el;
            } else if (sub.state == "reset") {
                time_el = admin2020.time_formatter.format(sub.sent_time);
            } else {
                time_el = admin2020.time_formatter.format(sub.submit_time);
            }

            var td = null;
            if (sub.state == "reset") {
                td = goog.dom.createDom("TD", "submit-blue");
                td.innerHTML = "Spam counter reset by <b>" + sub.user + "</b>.";
            } else {
                td = goog.dom.createDom("TD", {className: "submit-answer"}, sub.answer);
            }

            tr = goog.dom.createDom(
                "TR", {className: "submit-" + sub.color},
                td,
                goog.dom.createDom("TD", {className: "submit-time"}, time_el),
                goog.dom.createDom("TD", {className: "submit-state"},
                                   goog.dom.createDom("SPAN", null,
                                                      sub.state)));
            if (typeof twemoji !== 'undefined') {
              tr = twemoji.parse(tr);
            }
            this.tppsubmitbody.appendChild(tr);

            if (sub.response) {
                td = goog.dom.createDom("TD", {colSpan: 3});
                td.innerHTML = sub.response;
                tr = goog.dom.createDom("TR", {className: "submit-extra submit-" + sub.color}, td);
                this.tppsubmitbody.appendChild(tr);
            }
        }

        twemoji.parse(goog.dom.getElement("admincontent"));

        admin2020.counter.reread();
    }
}

class A2020_TaskQueue {
    constructor() {
        /** @type{Element|null} */
        this.queue = goog.dom.getElement("taskqueue");
        this.tbody = goog.dom.getElement("taskqueuedata");
        this.update_queue();
        this.last_response = null;

        var el = goog.dom.getElement("tqfilters");
        el.innerHTML = "";

        var kinds = ["hint", "visit", "penny", "phone"];
        var emoji = ["1f9ae", "2708", "1f7e4", "260e"];
        this.filter = {};

        var saved = [];
        var x = localStorage.getItem("tqfilter");
        if (x) {
            saved = x.split(",");
        } else {
            saved = kinds;
        }

        for (var i = 0; i < kinds.length; ++i) {
            var k = kinds[i];
            var e = eurl + emoji[i] + ".png";
            this.filter[k] = saved.includes(k);
            var cb = goog.dom.createDom("BUTTON", this.filter[k] ? "filterbox" : "filterbox off",
                                        goog.dom.createDom("IMG", {src: e}),
                                        goog.dom.createDom("BR"),
                                        k);
            goog.events.listen(cb, goog.events.EventType.CLICK,
                               goog.bind(this.toggle_filter, this, k));
            el.appendChild(cb);
        }

        this.sort_age = goog.dom.getElement("tqsort_age");
        this.sort_team = goog.dom.getElement("tqsort_team");
        goog.events.listen(this.sort_age, goog.events.EventType.CLICK,
                           goog.bind(this.change_sort, this, "age"));
        goog.events.listen(this.sort_team, goog.events.EventType.CLICK,
                           goog.bind(this.change_sort, this, "team"));
        this.sort_key = null;

        var sort = localStorage.getItem("tqsort");
        if (!sort) sort = "age";
        this.change_sort(sort, null);

        this.concierge_re = new RegExp("^t-[a-z0-9_]+-concierge-callback");

        this.comparators = {};
        this.comparators["age"] = function(a, b) { return a.when - b.when; };
        this.comparators["team"] = function(a, b) {
            if (a.team < b.team) {
                return -1;
            } else if (a.team > b.team) {
                return 1;
            } else {
                return 0;
            }
        };
    }

    change_sort(newsort, e) {
        if (this.sort_key == newsort) return;
        this.sort_key = newsort;
        if (newsort == "age") {
            goog.dom.classlist.remove(this.sort_age, "off");
            goog.dom.classlist.add(this.sort_team, "off");
        } else {
            goog.dom.classlist.add(this.sort_age, "off");
            goog.dom.classlist.remove(this.sort_team, "off");
        }
        if (e) {
            localStorage.setItem("tqsort", newsort);
            e.target.blur();
        }
        if (this.last_response) {
            this.render_queue(this.last_response);
        }
    }

    toggle_filter(kind, e) {
        this.filter[kind] = !this.filter[kind];
        if (this.filter[kind]) {
            goog.dom.classlist.remove(e.currentTarget, "off");
        } else {
            goog.dom.classlist.add(e.currentTarget, "off");
        }
        var save = ""
        for (var k in this.filter) {
            if (this.filter[k]) {
                save += k + ","
            }
        }
        localStorage.setItem("tqfilter", save);
        e.target.blur();
        this.render_queue(this.last_response);
    }

    update_queue() {
        goog.net.XhrIo.send("/admin/js/taskqueue",
                            Common_invoke_with_json(this, this.render_queue));
    }

    set_favicon_color(response, color) {
        var links = document.querySelectorAll("link[rel*='icon']");
        for (var i = 0; i < links.length; ++i) {
            links[i].href = response.favicons[color]["s" + links[i].getAttribute("sizes")];
        }
    }

    /** @param{TaskQueue} response */
    render_queue(response) {
        if (goog.DEBUG) {
            console.log(response);
        }
        this.last_response = response;
        if (!response || response.queue.length == 0) {
            this.tbody.innerHTML = "<tr><td colspan=6 style=\"padding: 20px;\">No tasks are waiting.</td></tr>"
            this.set_favicon_color(response, "green");
            return;
        }
        this.tbody.innerHTML = "";
        var now = (new Date()).getTime() / 1000.0;
        var count = 0;
        var unclaimed = 0;

        response.queue.sort(this.comparators[this.sort_key]);

        for (var i = 0; i < response.queue.length; ++i) {
            var msg = response.queue[i];
            if (!this.filter[msg.kind]) continue;
            ++count;

            var tqtime = goog.dom.createDom("TD", "tqtime counter", admin2020.time_formatter.duration(now-msg.when));
            tqtime.setAttribute("data-since", msg.when);
            var tqteam = goog.dom.createDom("TD", {className: "tqteam"}, msg.team);
            var claimlink = null;
            if (msg.claimant) {
                claimlink = goog.dom.createDom("BUTTON", "action", "Unclaim");
            } else {
                claimlink = goog.dom.createDom("BUTTON", "action", "Claim");
                ++unclaimed;
            }
            goog.events.listen(claimlink, goog.events.EventType.CLICK,
                               goog.bind(this.claim_task, this, msg));

            var claim_el = null;
            if (msg.claimant) {
                claim_el = goog.dom.createDom("TD", {className: "tqclaimant"}, msg.claimant);
            } else if (msg.last_sender) {
                claim_el = goog.dom.createDom("TD", {className: "tqlastsender"}, "(" + msg.last_sender + ")");
            }
            var what_el = null;
            if (msg.target) {
                what_el = goog.dom.createDom("A", {href: msg.target}, msg.what);
            } else {
                what_el = goog.dom.createDom("SPAN", null, msg.what);
            }

            var done_el = null;
            if (msg.key.charAt(0) == "t" && msg.key.search(this.concierge_re) < 0) {
                if (msg.done_pending) {
                    done_el = goog.dom.createDom("BUTTON", "inlineminiaction", "Undo done ");
                    var counter = goog.dom.createDom("SPAN", "counter");
                    counter.setAttribute("data-until-secs", ""+msg.done_pending);
                    done_el.appendChild(counter);
                    goog.dom.classlist.add(what_el, "strike");
                    goog.dom.classlist.add(tqtime, "strike");
                    goog.dom.classlist.add(tqteam, "strike");
                    goog.events.listen(done_el, goog.events.EventType.CLICK,
                                       goog.bind(this.uncomplete_task, this, msg));
                } else {
                    done_el = goog.dom.createDom("BUTTON", "inlineminiaction", "Mark done");
                    goog.events.listen(done_el, goog.events.EventType.CLICK,
                                       goog.bind(this.complete_task, this, msg));
                }
            }

            var tr = goog.dom.createDom(
                "TR", null,
                tqtime,
                tqteam,
                goog.dom.createDom("TD", {className: "tqwhat"}, what_el, done_el),
                goog.dom.createDom("TD", {className: "tqclaim"}, claimlink),
                claim_el);
            this.tbody.appendChild(tr);
        }
        admin2020.counter.reread();
        twemoji.parse(this.tbody);

        var color;
        if (count == 0) {
            this.tbody.innerHTML = "<tr><td colspan=6 style=\"padding: 20px;\">All tasks have been filtered out.</td></tr>";
            color = "green";
        } else if (unclaimed > 0) {
            color = "red";
        } else {
            color = "amber";
        }
        this.set_favicon_color(response, color);
    }

    claim_task(msg) {
        A2020_DoAction({action: "update_claim",
                        which: msg.claimant ? "unclaim" : "claim",
                        key: msg.key}, Common_expect_204);
    }

    complete_task(msg) {
        A2020_DoAction({action: "complete_task",
                        which: "done",
                        key: msg.key}, Common_expect_204);
    }

    uncomplete_task(msg) {
        A2020_DoAction({action: "complete_task",
                        which: "undone",
                        key: msg.key}, Common_expect_204);
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

        A2020_DoAction({action: "update_admin_role",
                        username: user,
                        role: role,
                        which: e.target.checked ? "set" : "clear"}, Common_expect_204);
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
        twemoji.parse(this.dropdown);
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

function A2020_DisplayLog(el, log) {
    if (!log || log.length == 0) {
        el.innerHTML = "No activity.";
        return;
    }
    el.innerHTML = "";
    for (var i = 0; i < log.length; ++i) {
        var e = log[i];
        var td = goog.dom.createDom("TD");
        for (var j = 0; j < e.htmls.length; ++j) {
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
}

class A2020_ServerPage {
    constructor() {
        /** @type{Element} */
        this.waits = goog.dom.getElement("stwaits");
        /** @type{Element} */
        this.sessions = goog.dom.getElement("stsessions");
        /** @type{Element} */
        this.proxy_waits = goog.dom.getElement("stproxies");

        this.flusher = new Common_enabler(
            "srvflushenable", "srvflush",
            function(e) { A2020_DoAction({action: "flush_template_cache"},
                                         Common_expect_204); });

        this.update();

        setInterval(goog.bind(this.update, this), 5000);
    }

    update() {
        goog.net.XhrIo.send("/admin/js/server",
                            Common_invoke_with_json(this, this.build));
    }

    /** param{ServerPageData} data */
    build(data) {
        this.waits.innerHTML = "" + data.waits;
        this.sessions.innerHTML = "" + data.sessions;
        this.proxy_waits.innerHTML = "";
        for (var i = 0; i < data.proxy_waits.length; ++i) {
            this.proxy_waits.appendChild(
                goog.dom.createDom("SPAN", "proxyload", ""+data.proxy_waits[i]));
        }
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
        /** @type{Element} */
        this.tpsvg = goog.dom.getElement("tpsvg");
        /** @type{Element} */
        this.tpscore = goog.dom.getElement("tpscore");
        /** @type{Element} */
        this.tpphone = goog.dom.getElement("tpphone");
        /** @type{Element} */
        this.tploc = goog.dom.getElement("tploc");

        this.pennypass = new Common_enabler(
            "tppassenable", "tppassbestow",
            function(e) { A2020_DoAction({action: "bestow_fastpass",
                                          team_username: team_username},
                                         Common_expect_204); });

        var el = goog.dom.getElement("tpaddnote");
        goog.events.listen(el, goog.events.EventType.CLICK, function() {
            var el = goog.dom.getElement("tpnotetext");
            var text = el.value;
            if (!text) return;
            A2020_DoAction({action: "add_note",
                            team_username: team_username,
                            text: text}, Common_expect_204);
            el.value = "";
        });

        var div = goog.dom.getElement("tplandlabels");
        for (var i = 0; i < label_info.lands.length; ++i) {
            var land = label_info.lands[i];
            var sp = goog.dom.createDom(
                "SPAN",
                {className: "landtag bblandtaghead",
                 style: "background-color: " + land.color + "; left: " + land.left + "px;"},
                land.symbol);
            div.appendChild(sp);
        }


        this.dot_labeler = new A2020_DotLabeler(this.tpsvg);

        this.update();
    }

    update() {
        goog.net.XhrIo.send("/admin/js/team/" + team_username,
                            Common_invoke_with_json(this, this.build));
    }

    /** param{TeamPageData} data */
    build(data) {
        this.tpopencount.innerHTML = "" + data.open_puzzles.length;

        var i, j;

        var el = this.tpopenlist;
        el.innerHTML = "";
        for (i = 0; i < data.open_puzzles.length; ++i) {
            var op = data.open_puzzles[i];
            if (i > 0) {
                el.appendChild(goog.dom.createDom("BR"));
            }
            var sp = goog.dom.createDom("SPAN", "landtag", op.symbol);
            sp.style.backgroundColor = op.color;
            el.appendChild(sp);

            el.appendChild(goog.dom.createTextNode(" "));

            el.appendChild(goog.dom.createDom(
                "A", {href: "/admin/team/" + team_username + "/puzzle/" + op.shortname},
                op.title));

            el.appendChild(goog.dom.createTextNode(" ("));
            sp = goog.dom.createDom("SPAN", "counter");
            sp.setAttribute("data-since", op.open_time);
            el.appendChild(sp);
            el.appendChild(goog.dom.createTextNode(")"));
            if ("answers_found" in op) {
                el.appendChild(goog.dom.createTextNode(" \u2014 "));
                for (j = 0; j < op.answers_found.length; ++j) {
                    if (j > 0) {
                        el.appendChild(goog.dom.createTextNode(", "));
                    }
                    el.appendChild(goog.dom.createDom("SPAN", "answer", op.answers_found[j]));
                }
            }
        }

        el = this.tpfastpass;
        el.innerHTML = "";
        if (data.fastpasses && data.fastpasses.length > 0) {
            el.style.display = "inline";
            for (i = 0; i < data.fastpasses.length; ++i) {
                if (i > 0) {
                    el.appendChild(goog.dom.createTextNode(", "));
                }
                var sp = goog.dom.createDom("SPAN", "counter");
                sp.setAttribute("data-until", data.fastpasses[i]);
                el.appendChild(sp);
            }
        } else {
            el.style.display = "none";
        }

        A2020_DisplayLog(this.tplog, data.log);

        this.tpsvg.innerHTML = data.svg;
        this.tpscore.innerHTML = "" + data.score;
        this.tpphone.innerHTML = data.phone;
        this.tploc.innerHTML = data.location;

        twemoji.parse(goog.dom.getElement("admincontent"));

        admin2020.counter.reread();
    }
}

class A2020_PuzzlePage {
    constructor() {
        /** @type{Element} */
        this.ppopencount = goog.dom.getElement("ppopencount");
        /** @type{Element} */
        this.ppsubmittedcount = goog.dom.getElement("ppsubmittedcount");
        /** @type{Element} */
        this.ppsolvedcount = goog.dom.getElement("ppsolvedcount");
        /** @type{Element} */
        this.ppmediansolve = goog.dom.getElement("ppmediansolve");
        /** @type{Element} */
        this.ppbadsubmit = goog.dom.getElement("ppbadsubmit");
         /** @type{Element} */
        this.pplog = goog.dom.getElement("pplog");
         /** @type{Element} */
        this.pphinttime = goog.dom.getElement("pphinttime");
         /** @type{Element} */
        this.pperrata = goog.dom.getElement("pperrata");
         /** @type{Element} */
        this.pperratalist = goog.dom.getElement("pperratalist");
         /** @type{Element} */
        this.pphintreplies = goog.dom.getElement("pphintreplies");
         /** @type{Element} */
        this.pphintreplylist = goog.dom.getElement("pphintreplylist");

        var el = goog.dom.getElement("hinttimechange");
        goog.events.listen(el, goog.events.EventType.CLICK, function() {
            goog.dom.getElement("hinttimechange").style.display = "none";
            goog.dom.getElement("hinttimechangeentry").style.display = "inline";
        });
        goog.events.listen(
            goog.dom.getElement("newhinttimesubmit"),
            goog.events.EventType.CLICK,
            function() {
                var text = goog.dom.getElement("newhinttime").value;
                A2020_DoAction({action: "update_hint_time",
                                puzzle_id: puzzle_id,
                                hint_time: text},
                               Common_expect_204);
                goog.dom.getElement("hinttimechange").style.display = "initial";
                goog.dom.getElement("hinttimechangeentry").style.display = "none";
            });

        this.update();
    }

    update() {
        goog.net.XhrIo.send("/admin/js/puzzle/" + puzzle_id,
                            Common_invoke_with_json(this, this.build));
    }

    /** param{PuzzlePageData} data */
    build(data) {
        this.ppopencount.innerHTML = "" + data.open_count;
        this.ppsubmittedcount.innerHTML = "" + data.submitted_count;
        this.ppsolvedcount.innerHTML = "" + data.solve_count;
        if (data.solve_count > 0) {
            this.ppmediansolve.innerHTML = admin2020.time_formatter.duration(data.median_solve);
        } else {
            this.ppmediansolve.innerHTML = "\u2014";
        }

        this.ppbadsubmit.innerHTML = "";
        for (var i = 0; i < data.incorrect_answers.length; ++i) {
            if (i > 0) {
                this.ppbadsubmit.appendChild(goog.dom.createDom("BR"));
            }
            this.ppbadsubmit.appendChild(goog.dom.createDom("SPAN", "badsubmitcount", ""+data.incorrect_answers[i][0]));
            this.ppbadsubmit.appendChild(goog.dom.createTextNode(": "));
            this.ppbadsubmit.appendChild(goog.dom.createDom("SPAN", "badsubmit", ""+data.incorrect_answers[i][1]));
        }

        this.pphinttime.innerHTML = admin2020.time_formatter.duration(data.hint_time);

        A2020_DisplayLog(this.pplog, data.log);

        if (data.errata && data.errata.length > 0) {
            this.pperrata.style.display = "block";
            this.pperratalist.innerHTML = ""
            A2020_ErrataPage.append_errata(this.pperratalist, data.errata);
        } else {
            this.pperrata.style.display = "none";
        }

        if (data.hint_replies && data.hint_replies.length > 0) {
            this.pphintreplies.style.display = "block";
            this.pphintreplylist.innerHTML = "";
            for (var i = 0; i < data.hint_replies.length; ++i) {
                var msg = data.hint_replies[i];
                var dt = goog.dom.createDom(
                    "DT", null,
                    admin2020.time_formatter.format(msg.when) + " ",
                    goog.dom.createDom("B", null, msg.sender),
                    " to " + msg.team);
                var dd = goog.dom.createDom("DD")
                dd.innerHTML = msg.text;
                this.pphintreplylist.appendChild(dt);
                this.pphintreplylist.appendChild(dd);
            }
        } else {
            this.pphintreplies.style.display = "none";
        }

        twemoji.parse(goog.dom.getElement("admincontent"));

        admin2020.counter.reread();
    }
}

class A2020_DotLabeler {
    constructor(click_div) {
        this.tooltip = null;
        this.tooltip_timer = null;
        this.by_bbid = {};
        for (var i = 0; i < puzzle_list.length; ++i) {
            this.by_bbid[""+puzzle_list[i][2]] = puzzle_list[i][1];
        }
        goog.events.listen(click_div, goog.events.EventType.CLICK,
                           goog.bind(this.on_click, this));
    }

    on_click(e) {
        this.remove_tooltip();
        var classes = goog.dom.classlist.get(e.target);
        for (var i = 0; i < classes.length; ++i) {
            var k = classes[i];
            if (k.startsWith("bbp-")) {
                var title = this.by_bbid[k.substring(4)];
                var x = e.clientX + window.pageXOffset + 4;
                var y = e.clientY + window.pageYOffset - 32;
                if (y < 100) y += 36;
                this.tooltip = goog.dom.createDom("DIV", {
                    className: "bbtooltip",
                    style: "left: " + x + "px; top: " + y + "px;"}, title);
                document.body.appendChild(this.tooltip);

                this.tooltip_timer = setTimeout(goog.bind(this.remove_tooltip, this), 1000);
                break;
            }
        }
    }

    remove_tooltip() {
        if (this.tooltip_timer) {
            clearTimeout(this.tooltip_timer);
            this.tooltip_timer = null;
        }
        if (this.tooltip) {
            this.tooltip.remove();
            this.tooltip = null;
        }
    }
}

class A2020_BigBoard {
    constructor() {
        /** @type{Element} */
        this.taskqueue = goog.dom.getElement("bbtaskqueue");
        this.refresh_taskqueue();

        this.team_data = {};
        this.team_els = [];

        /** @type{Element} */
        this.teamdiv = goog.dom.getElement("bbteams");

        var div = goog.dom.getElement("bblandlabels");

        for (var i = 0; i < label_info.lands.length; ++i) {
            var land = label_info.lands[i];
            var sp = goog.dom.createDom(
                "SPAN",
                {className: "landtag bblandtaghead",
                 style: "background-color: " + land.color + "; left: " + land.left + "px;"},
                land.symbol);
            div.appendChild(sp);
        }

        goog.net.XhrIo.send("/admin/js/bbteam",
                            Common_invoke_with_json(this, this.update_all_teams));

        this.dot_labeler = new A2020_DotLabeler(this.teamdiv);
    }

    /** @param{Object<string, BBTeamData>} data */
    update_all_teams(data) {
        this.team_data = data;
        this.team_els = [];

        for (var i = 0; i < team_list.length; ++i) {
            var username = team_list[i][0];
            var d = this.team_data[username];

            var score = goog.dom.createDom("DIV", "bb-score", "" + d.score);
            if (d.remote) {
                score.appendChild(goog.dom.createDom("BR"));
                score.appendChild(goog.dom.createDom("IMG", {src: d.remote}));
            }
            var name = goog.dom.createDom("DIV", "bb-name", team_list[i][1]);
            var svg = goog.dom.createDom("DIV", "bb-svg");
            svg.innerHTML = d.svg;

            var el = goog.dom.createDom("DIV", "bb-row", score, name, svg);
            el.setAttribute("data-username", d.username);

            d.el = el;
            this.team_els.push(el);
        }

        this.reorder_teams();
    }

    /** @param{string} username */
    refresh_team(username) {
        // Can't refresh until we have the initial data.
        if (this.team_data === null) return;

        goog.net.XhrIo.send("/admin/js/bbteam/" + username,
                            Common_invoke_with_json_arg(this, this.update_one_team, username));
    }

    /** @param{string} username */
    /** @param{BBTeamData} data */
    update_one_team(username, data) {
        var el = this.team_data[username].el;
        this.team_data[username] = data;
        this.team_data[username].el = el;

        var score = el.firstChild;
        score.innerHTML = "" + data.score;
        if (data.remote) {
            score.appendChild(goog.dom.createDom("BR"));
            score.appendChild(goog.dom.createDom("IMG", {src: data.remote}));
        }

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
        twemoji.parse(this.teamdiv);
    }

    refresh_taskqueue() {
        goog.net.XhrIo.send("/admin/js/bbtaskqueue",
                            Common_invoke_with_json(this, this.update_taskqueue));
    }

    /** @param{BBTaskQueue} data */
    update_taskqueue(data) {
        if (!data) return;
        var bk = data.by_kind;
        this.taskqueue.innerHTML =
            "<img src=\"" + eurl + "1f9ae.png\"> " + bk["hint"][0] + "/" + bk["hint"][1] + " &nbsp; " +
            "<img src=\"" + eurl + "2708.png\"> " + bk["visit"][0] + "/" + bk["visit"][1] + " &nbsp; " +
            "<img src=\"" + eurl + "1f7e4.png\"> " + bk["penny"][0] + "/" + bk["penny"][1] + " &nbsp; " +
            "<img src=\"" + eurl + "260e.png\"> " + bk["phone"][0] + "/" + bk["phone"][1];
    }
}

var admin2020 = {
    waiter: null,
    counter: null,
    taskqueue: null,
    time_formatter: null,
    serializer: null,
    puzzle_select: null,
    team_select: null,
    user_roles: null,
    bigboard: null,
    team_page: null,
    puzzle_page: null,
    team_puzzle_page: null,
    server_page: null,
    team_list_page: null,
    puzzle_list_page: null,
    fix_puzzle: null,
    home_page: null,
    errata_page: null,
    lands_page: null,
}

window.onload = function() {
    admin2020.serializer = new goog.json.Serializer();
    admin2020.waiter = new Common_Waiter(
        new A2020_Dispatcher(), "/adminwait", received_serial, sessionStorage,
        function(text) {
            alert(text);
        });
    admin2020.waiter.start();

    admin2020.time_formatter = new Common_TimeFormatter();
    admin2020.counter = new Common_Counter(admin2020.time_formatter);

    if (goog.dom.getElement("taskqueue")) {
        admin2020.taskqueue = new A2020_TaskQueue();
    }

    var el;

    el = goog.dom.getElement("puzzleselect");
    if (el) {
        admin2020.puzzle_select = new A2020_Autocomplete(
            el, puzzle_list,
            function(shortname) {
                if (team_username && !el.getAttribute("data-top")) {
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
                if (puzzle_id && !el.getAttribute("data-top")) {
                    window.location.href = "/admin/team/" + username + "/puzzle/" + puzzle_id;
                } else {
                    window.location.href = "/admin/team/" + username;
                }
            });
    }

    el = goog.dom.getElement("navpuzzleselect");
    if (el) {
        admin2020.puzzle_select = new A2020_Autocomplete(
            el, puzzle_list,
            function(shortname) {
                window.location.href = "/admin/puzzle/" + shortname;
            });
    }

    el = goog.dom.getElement("navteamselect");
    if (el) {
        admin2020.team_select = new A2020_Autocomplete(
            el, team_list,
            function(username) {
                window.location.href = "/admin/team/" + username;
            });
    }

    if (page_class == "AdminUsersPage") {
        admin2020.user_roles = new A2020_UserRoles()
    }
    if (page_class == "BigBoardPage") {
        admin2020.bigboard = new A2020_BigBoard();
    }
    if (page_class == "AdminServerPage") {
        admin2020.server_page = new A2020_ServerPage();
    }
    if (page_class == "FixPuzzlePage") {
        admin2020.fix_puzzle = new A2020_FixPuzzlePage();
    }
    if (page_class == "TeamPage") {
        admin2020.team_page = new A2020_TeamPage();
    }
    if (page_class == "PuzzlePage") {
        admin2020.puzzle_page = new A2020_PuzzlePage();
    }
    if (page_class == "TeamPuzzlePage") {
        admin2020.team_puzzle_page = new A2020_TeamPuzzlePage();
    }
    if (page_class == "ListTeamsPage") {
        admin2020.team_list_page = new A2020_ListTeamsPage();
    }
    if (page_class == "ListPuzzlesPage") {
        admin2020.puzzle_list_page = new A2020_ListPuzzlesPage();
    }
    if (page_class == "AdminHomePage") {
        admin2020.home_page = new A2020_HomePage();
    }
    if (page_class == "ErrataPage") {
        admin2020.errata_page = new A2020_ErrataPage();
    }
    if (page_class == "LandsPage") {
        admin2020.lands_page = new A2020_LandsPage();
    }
    if (page_class == "PuzzleContentPage") {
        if (typeof puzzle_init !== 'undefined' && puzzle_init) puzzle_init();
    }
}

class A2020_FixPuzzlePage {
    constructor() {
        /** @type{Element} */
        this.fixenable = goog.dom.getElement("fixenable");
        /** @type{Element} */
        this.fixsubmit = goog.dom.getElement("fixsubmit");
        /** @type{Element} */
        this.fixresult = goog.dom.getElement("fixresult");
        /** @type{Element} */
        this.fixdopost = goog.dom.getElement("fixdopost");
        /** @type{Element} */
        this.fixdoreload = goog.dom.getElement("fixdoreload");
        /** @type{Element} */
        this.fixtext = goog.dom.getElement("fixtext");
        /** @type{Element} */
        this.fixpreview = goog.dom.getElement("fixpreview");

        this.dirty = false;

        var b = goog.bind(this.enable, this);
        goog.events.listen(this.fixdopost, goog.events.EventType.CHANGE, b);
        if (this.fixdoreload) {
            goog.events.listen(this.fixdoreload, goog.events.EventType.CHANGE, b);
        }
        goog.events.listen(this.fixenable, goog.events.EventType.CLICK, b);

        goog.events.listen(this.fixtext, goog.events.EventType.INPUT,
                           goog.bind(this.mark_dirty, this));

        goog.events.listen(this.fixsubmit, goog.events.EventType.CLICK,
                           goog.bind(this.submit, this));

        setInterval(goog.bind(this.show_preview, this), 1000);
    }

    enable(e) {
        this.fixtext.disabled = !this.fixdopost.checked;

        if (this.fixdopost.checked || (this.fixdoreload && this.fixdoreload.checked)) {
            if (e.target == this.fixenable) {
                this.fixsubmit.disabled = !this.fixsubmit.disabled;
            } else {
                this.fixenable.disabled = false;
            }
        } else {
            this.fixenable.disabled = true;
            this.fixsubmit.disabled = true;
        }
    }

    mark_dirty() {
        this.dirty = true;
    }

    show_preview() {
        if (this.dirty) {
            this.fixpreview.innerHTML = this.fixtext.value;
            this.dirty = false;
        }
    }

    submit() {
        this.fixenable.disabled = true;
        this.fixsubmit.disabled = true;

        var d = {"action": "fix_puzzle", "puzzle_id": puzzle_id};
        if (this.fixdopost.checked) {
            d["text"] = this.fixtext.value;
        }
        if (this.fixdoreload && this.fixdoreload.checked) {
            d["reload"] = true;
        }
        A2020_DoAction(d, Common_invoke_with_json(this, this.submit_result));
    }

    submit_result(data) {
        if (data.success) {
            goog.dom.classlist.addRemove(this.fixresult, "failure", "success");
            this.fixresult.innerHTML = data.message;
        } else {
            goog.dom.classlist.addRemove(this.fixresult, "success", "failure");
            this.fixresult.innerHTML = data.message;
        }
    }
}

class A2020_HomePage {
    constructor() {
        this.pennypass_all = new Common_enabler(
            "hppassenable", "hppassbestow",
            function() { A2020_DoAction({action: "bestow_fastpass"},
                                        Common_expect_204); });

        this.pennypass_remote = new Common_enabler(
            "hppassremoteenable", "hppassremotebestow",
            function() { A2020_DoAction({action: "bestow_fastpass",
                                         remote_only: true},
                                        Common_expect_204); });

        this.openlands_all = new Common_enabler(
            "hplandenable", "hplandopen",
            function() { A2020_DoAction({action: "open_all_lands"},
                                        Common_expect_204); });

        this.openpuzzles_all = new Common_enabler(
            "hppuzzenable", "hppuzzopen",
            function() { A2020_DoAction({action: "open_all_puzzles"},
                                        Common_expect_204); });
        this.closehunt = new Common_enabler(
            "hpcloseenable", "hpclosehunt",
            function() { A2020_DoAction({action: "close_hunt"},
                                        Common_expect_204); });
    }
}

class A2020_ErrataPage {
    constructor() {
        /** @type{Element} */
        this.eperrata = goog.dom.getElement("errata");

        this.update();
    }

    update() {
        goog.net.XhrIo.send("/admin/js/errata", Common_invoke_with_json(this, this.build));
    }

    /** param{Array<Erratum>} data */
    build(data) {
        if (data.length == 0) {
            this.eperrata.innerHTML = "Nothing so far. (Fingers crossed!)";
        } else {
            this.eperrata.innerHTML = "";
            A2020_ErrataPage.append_errata(this.eperrata, data);
        }
    }

    static append_errata(el, data) {
        var last_when = 0;
        for (var i = 0; i < data.length; ++i) {
            var e = data[i];

            if (e.when - last_when > 1.0) {
                var dt = goog.dom.createDom(
                    "DT", null,
                    goog.dom.createDom("A", {href: "/admin/puzzle/" + e.puzzle_id}, e.title),
                    " (posted " + admin2020.time_formatter.format(e.when) + " by " + e.sender + ")");
                el.appendChild(dt);
            }
            last_when = e.when;

            var dd;
            if (e.text) {
                dd = goog.dom.createDom("DD", null);
                dd.innerHTML = e.text;
            } else {
                dd = goog.dom.createDom("DD", "reload");
                dd.innerHTML = "Puzzle was reloaded.";
            }
            el.appendChild(dd);
        }
    }
}

class A2020_LandsPage {
    constructor() {
        this.update = new Common_enabler(
            "lpenable", "lpupdate", goog.bind(this.send_update, this));
        for (var el of document.querySelectorAll("table input")) {
            goog.events.listen(el, goog.events.EventType.KEYDOWN,
                               e => goog.dom.classlist.add(e.currentTarget, "modified"));
        }
    }

    send_update() {
        var inputs = document.querySelectorAll("table input");
        var d = {action: "update_lands"}
        var empty = true;
        for (var input of inputs) {
            d[input.id] = input.value;
            empty = false;
        }
        if (empty) return;
        A2020_DoAction(d, Common_invoke_with_json(this, this.update_result));
    }

    /** param{LandResponse} */
    update_result(data) {
        if (goog.DEBUG) {
            console.log(data);
        }
        var result = goog.dom.getElement("result");
        result.innerHTML = "";
        goog.dom.classlist.add(result, data.success ? "success" : "failure");
        for (const text of data.messages) {
            result.appendChild(goog.dom.createDom("LI", null, text));
        }
        if (data.success) {
            result.appendChild(goog.dom.createDom(
                "LI", null, goog.dom.createDom(
                    "B", null, "Refresh page to see updated values.")));
        }
    }
}

class A2020_ListPuzzlesPage {
    constructor() {
        /** @type{Element} */
        this.plbody = goog.dom.getElement("plbody");

        this.comparators = {}
        this.comparators["title"] = function(a, b) {
            if (a.title_sort < b.title_sort) {
                return -1;
            } else if (a.title_sort > b.title_sort) {
                return 1;
            } else {
                return 0;
            }
        };
        this.comparators["order"] = function(a, b) { return a.order - b.order; };
        this.comparators["open"] = function(a, b) { return a.open_count - b.open_count; };
        this.comparators["submitted"] = function(a, b) { return a.submitted_count - b.submitted_count; };
        this.comparators["incorrect"] = function(a, b) { return a.incorrect_count - b.incorrect_count; };
        this.comparators["solved"] = function(a, b) { return a.solved_count - b.solved_count; };
        this.comparators["mediansolve"] = function(a, b) {
            return (a.median_solve ? a.median_solve : 1000000) -
                (b.median_solve ? b.median_solve : 1000000);
        }
        this.comparators["unsolved"] = function(a, b) { return a.unsolved_count - b.unsolved_count; };
        this.comparators["hint"] = function(a, b) { return a.hint_time - b.hint_time; };

        for (var k in this.comparators) {
            var el = goog.dom.getElement("plsort_" + k);
            goog.events.listen(el, goog.events.EventType.CLICK,
                               goog.bind(this.change_sort, this, k));
        }
        this.sort_key = null;
        this.sort_reverse = false;
        this.change_sort("order", null);

        this.last_response = null;


        this.update();
    }

    change_sort(newsort, e) {
        if (this.sort_key == newsort) {
            this.sort_reverse = !this.sort_reverse;
            if (this.sort_reverse) {
                goog.dom.classlist.add(goog.dom.getElement("plsort_" + newsort), "sortup");
                goog.dom.classlist.remove(goog.dom.getElement("plsort_" + newsort), "sortdown");
            } else {
                goog.dom.classlist.add(goog.dom.getElement("plsort_" + newsort), "sortdown");
                goog.dom.classlist.remove(goog.dom.getElement("plsort_" + newsort), "sortup");
            }
        } else {
            this.sort_key = newsort;
            this.sort_reverse = false;
            for (var k in this.comparators) {
                if (k == newsort) {
                    if (this.sort_reverse) {
                        goog.dom.classlist.add(goog.dom.getElement("plsort_" + k), "sortup");
                    } else {
                        goog.dom.classlist.add(goog.dom.getElement("plsort_" + k), "sortdown");
                    }
                } else {
                    goog.dom.classlist.remove(goog.dom.getElement("plsort_" + k), "sortup");
                    goog.dom.classlist.remove(goog.dom.getElement("plsort_" + k), "sortdown");
                }
            }
        }

        if (e) {
            e.target.blur();
        }
        if (this.last_response) {
            this.render(this.last_response);
        }
    }

    update() {
        goog.net.XhrIo.send("/admin/js/puzzles", Common_invoke_with_json(this, this.render));
    }

    number(n) {
        if (n) {
            return goog.dom.createDom("TD", "r", ""+n);
        } else {
            return goog.dom.createDom("TD", "r z", "-");
        }
    }

    /** param{Array<ListPuzzleData>} data */
    render(data) {
        this.plbody.innerHTML = "";

        this.last_response = data;

        data.sort(this.comparators[this.sort_key]);
        if (this.sort_reverse) {
            data.reverse();
        }

        var i = 0;
        for (const row of data) {
            i += 1;

            var tr = goog.dom.createDom("TR", (i%3==0) ? "h" : null);

            var sp = goog.dom.createDom(
                "SPAN",
                {className: "landtag",
                 style: "background-color: " + row.color},
                row.symbol);

            tr.appendChild(goog.dom.createDom("TD", "c", sp));
            tr.appendChild(goog.dom.createDom("TD", null,
                                              goog.dom.createDom("A", {href: row.url}, row.title)));
            tr.appendChild(this.number(row.open_count));
            tr.appendChild(this.number(row.submitted_count));
            tr.appendChild(this.number(row.incorrect_count));
            tr.appendChild(this.number(row.solved_count));
            tr.appendChild(goog.dom.createDom("TD", row.median_solve ? "r" : "r z",
                                              row.median_solve ?
                                              admin2020.time_formatter.duration(row.median_solve) : "-"));
            tr.appendChild(this.number(row.unsolved_count));
            tr.appendChild(goog.dom.createDom("TD", row.hint_time_auto ? "r" : "r manual",
                                              admin2020.time_formatter.duration(row.hint_time)));
            this.plbody.appendChild(tr);
        }

        twemoji.parse(this.plbody);
    }
}

class A2020_ListTeamsPage {
    constructor() {
        /** @type{Element} */
        this.tlbody = goog.dom.getElement("tlbody");

        this.comparators = {}
        this.comparators["name"] = function(a, b) {
            if (a.name_sort < b.name_sort) {
                return -1;
            } else if (a.name_sort > b.name_sort) {
                return 1;
            } else {
                return 0;
            }
        };
        this.comparators["score"] = function(a, b) { return a.score - b.score; };
        this.comparators["pennies"] = function(a, b) {
            if (a.pennies[0] != b.pennies[0]) {
                return a.pennies[0] - b.pennies[0];
            } else {
                return a.pennies[1] - b.pennies[1];
            }
        };
        this.comparators["beam"] = function(a, b) { return a.beam - b.beam; };
        this.comparators["fastpass"] = function(a, b) { return a.fastpass - b.fastpass; };
        this.comparators["submits"] = function(a, b) { return a.submits_hr - b.submits_hr; };
        this.comparators["solves"] = function(a, b) { return a.solves_hr - b.solves_hr; };
        this.comparators["lastsubmit"] = function(a, b) { return a.last_submit - b.last_submit; };
        this.comparators["lastsolve"] = function(a, b) { return a.last_solve - b.last_solve; };


        for (var k in this.comparators) {
            var el = goog.dom.getElement("tlsort_" + k);
            goog.events.listen(el, goog.events.EventType.CLICK,
                               goog.bind(this.change_sort, this, k));
        }
        this.sort_key = null;
        this.sort_reverse = false;
        this.change_sort("name", null);

        this.last_response = null;

        this.update();
    }

    change_sort(newsort, e) {
        if (this.sort_key == newsort) {
            this.sort_reverse = !this.sort_reverse;
            if (this.sort_reverse) {
                goog.dom.classlist.add(goog.dom.getElement("tlsort_" + newsort), "sortup");
                goog.dom.classlist.remove(goog.dom.getElement("tlsort_" + newsort), "sortdown");
            } else {
                goog.dom.classlist.add(goog.dom.getElement("tlsort_" + newsort), "sortdown");
                goog.dom.classlist.remove(goog.dom.getElement("tlsort_" + newsort), "sortup");
            }
        } else {
            this.sort_key = newsort;
            this.sort_reverse = false;
            for (var k in this.comparators) {
                if (k == newsort) {
                    if (this.sort_reverse) {
                        goog.dom.classlist.add(goog.dom.getElement("tlsort_" + k), "sortup");
                    } else {
                        goog.dom.classlist.add(goog.dom.getElement("tlsort_" + k), "sortdown");
                    }
                } else {
                    goog.dom.classlist.remove(goog.dom.getElement("tlsort_" + k), "sortup");
                    goog.dom.classlist.remove(goog.dom.getElement("tlsort_" + k), "sortdown");
                }
            }
        }

        if (e) {
            e.target.blur();
        }
        if (this.last_response) {
            this.render(this.last_response);
        }
    }

    update() {
        goog.net.XhrIo.send("/admin/js/teams", Common_invoke_with_json(this, this.render));
    }

    number(n) {
        if (n) {
            return goog.dom.createDom("TD", "r", ""+n);
        } else {
            return goog.dom.createDom("TD", "r z", "-");
        }
    }

    timestamp(n) {
        if (n) {
            return goog.dom.createDom("TD", "r lp", admin2020.time_formatter.format(n));
        } else {
            return goog.dom.createDom("TD", "r z", "-");
        }
    }

    /** param{Array<ListTeamData>} data */
    render(data) {
        this.tlbody.innerHTML = "";

        this.last_response = data;

        data.sort(this.comparators[this.sort_key]);
        if (this.sort_reverse) {
            data.reverse();
        }

        var i = 0;
        for (const row of data) {
            i += 1;

            var tr = goog.dom.createDom("TR", (i%3==0) ? "h" : null);

            var el;
            if (row.remote) {
                el = goog.dom.createDom("IMG", {src: row.remote});
            } else {
                el = goog.dom.createDom("SPAN", "local");
            }
            var td = goog.dom.createDom("TD", "limit",
                                        goog.dom.createDom("A", {href: row.url}, el, row.name))
            tr.appendChild(td);

            tr.appendChild(this.number(row.score));
            if (row.pennies[2] == 0) {
                tr.appendChild(this.number(row.pennies[1]));
            } else {
                var text = "(" + row.pennies[2] + ") " + row.pennies[1];
                tr.appendChild(goog.dom.createDom("TD", "r", text));
            }
            tr.appendChild(this.number(row.beam));
            tr.appendChild(this.number(row.fastpass));
            tr.appendChild(this.number(row.submits_hr));
            tr.appendChild(this.number(row.solves_hr));
            tr.appendChild(this.timestamp(row.last_submit));
            tr.appendChild(this.timestamp(row.last_solve));
            this.tlbody.appendChild(tr);
        }

        twemoji.parse(this.tlbody);
    }
}
