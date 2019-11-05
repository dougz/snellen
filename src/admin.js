goog.require("goog.dom");
goog.require("goog.dom.classlist");
goog.require("goog.events");
goog.require("goog.events.KeyCodes");
goog.require("goog.net.XhrIo");
goog.require("goog.json.Serializer");

class A2020_Dispatcher {
    constructor() {
        this.methods = {
            "task_queue": this.task_queue,
            "update": this.update,
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
        this.for_ops = goog.dom.getElement("for_ops");

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
        this.tpplog = goog.dom.getElement("tpplog");

        goog.events.listen(goog.dom.getElement("tpphintreply"),
                           goog.events.EventType.CLICK, goog.bind(this.submit, this));

        goog.events.listen(this.claimlink, goog.events.EventType.CLICK,
                           goog.bind(this.do_claim, this, "claim"));
        goog.events.listen(this.unclaimlink, goog.events.EventType.CLICK,
                           goog.bind(this.do_claim, this, "unclaim"));

        this.update();
    }

    do_claim(which) {
        goog.net.XhrIo.send("/admin/" + which + "/h-" + team_username + "-" + puzzle_id,
                            A2020_expect_204);
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
        }, "POST", admin2020.serializer.serialize({"team_username": team_username,
                                                   "puzzle_id": puzzle_id,
                                                   "text": text}));
    }

    update() {
        goog.net.XhrIo.send(
            "/admin/js/teampuzzle/" + team_username + "/" + puzzle_id,
            goog.bind(function(e) {
                var code = e.target.getStatus();
                if (code == 200) {
                    this.build(e.target.getResponseJson());
                } else {
                    alert(e.target.getResponseText());
                }
            }, this));
    }

    /** @param{TeamPuzzlePageData} data */
    build(data) {
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

        console.log(data);
        console.log(this.replycontainer);
        if (data.hints_open) {
            this.replycontainer.style.display = "initial";
            this.for_ops.style.display = "block";

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
                    var dd = goog.dom.createDom("DD", null);
                    dd.innerHTML = msg.text;
                    dl.appendChild(dt);
                    dl.appendChild(dd);
                }
                this.history.appendChild(dl);
            }
        } else {
            this.history.innerHTML = "<i>Hints are not available for this team and puzzle.</i>";
            this.replycontainer.style.display = "none";
            this.for_ops.style.display = "none";
        }

        A2020_DisplayLog(this.tpplog, data.log);

        admin2020.counter.reread();
    }
}

class A2020_TaskQueue {
    constructor() {
        /** @type{Element|null} */
        this.queue = goog.dom.getElement("taskqueue");
        this.tbody = goog.dom.getElement("taskqueuedata");
        this.update_queue();
    }

    update_queue() {
        goog.net.XhrIo.send("/admin/taskqueuedata", goog.bind(function(e) {
            var code = e.target.getStatus();
            if (code == 200) {
                var response = /** @type{TaskQueue} */ (e.target.getResponseJson());
                this.render_queue(response);
            }
        }, this));
    }

    /** @param{TaskQueue} response */
    render_queue(response) {
        if (response.queue.length == 0) {
            this.tbody.innerHTML = "<tr><td colspan=6 style=\"padding: 20px;\">No tasks are waiting.</td></tr>"
            return;
        }
        this.tbody.innerHTML = "";
        var now = (new Date()).getTime() / 1000.0;
        for (var i = 0; i < response.queue.length; ++i) {
            var msg = response.queue[i];
            var tqtime = goog.dom.createDom("TD", "tqtime counter", admin2020.time_formatter.duration(now-msg.when));
            tqtime.setAttribute("data-since", msg.when);
            var tqteam = goog.dom.createDom("TD", {className: "tqteam"}, msg.team);
            var claimlink = null;
            if (msg.claimant) {
                claimlink = goog.dom.createDom("BUTTON", "action", "Unclaim");
            } else {
                claimlink = goog.dom.createDom("BUTTON", "action", "Claim");
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
                what_el = goog.dom.createDom("A", {href: msg.target, target: "_blank"}, msg.what);
            } else {
                what_el = goog.dom.createDom("SPAN", null, msg.what);
            }

            var done_el = null;
            if (msg.key.charAt(0) == "t") {
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
    }

    claim_task(msg) {
        var url = "/admin/" + (msg.claimant ? "unclaim" : "claim") + "/" + msg.key;
        goog.net.XhrIo.send(url, A2020_expect_204);
    }

    complete_task(msg) {
        var url = "/admin/complete/" + msg.key;
        goog.net.XhrIo.send(url, A2020_expect_204);
    }

    uncomplete_task(msg) {
        var url = "/admin/uncomplete/" + msg.key;
        goog.net.XhrIo.send(url, A2020_expect_204);
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

function A2020_expect_204(e) {
    var code = e.target.getStatus();
    if (code != 204) {
        alert(e.target.getResponseText());
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

        this.update();

        setInterval(goog.bind(this.update, this), 5000);
    }

    update() {
        goog.net.XhrIo.send("/admin/js/server", goog.bind(function(e) {
            var code = e.target.getStatus();
            if (code == 200) {
                this.build(e.target.getResponseJson());
            } else if (code != 502) {
                alert(e.target.getResponseText());
            }
        }, this));
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

        var el;

        el = goog.dom.getElement("bestowfastpass");
        goog.events.listen(el, goog.events.EventType.CLICK, function(e) {
            goog.net.XhrIo.send("/admin/bestowfastpass/" + team_username, A2020_expect_204);
            e.target.blur();
        });

        el = goog.dom.getElement("tpaddnote");
        goog.events.listen(el, goog.events.EventType.CLICK, function() {
            var el = goog.dom.getElement("tpnotetext");
            var text = el.value;
            if (!text) return;
            goog.net.XhrIo.send("/admin/addnote", A2020_expect_204,
                                "POST", admin2020.serializer.serialize({"team_username": team_username,
                                                                        "note": text}));
            el.value = "";
        });

        this.update();
    }

    update() {
        goog.net.XhrIo.send("/admin/js/team/" + team_username, goog.bind(function(e) {
            var code = e.target.getStatus();
            if (code == 200) {
                this.build(e.target.getResponseJson());
            } else {
                alert(e.target.getResponseText());
            }
        }, this));
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

        A2020_DisplayLog(this.tplog, data.log);

        admin2020.counter.reread();
    }
}

class A2020_PuzzlePage {
    constructor() {
        /** @type{Element} */
        this.ppsolvecount = goog.dom.getElement("ppsolvecount");
        /** @type{Element} */
        this.ppsolvelist = goog.dom.getElement("ppsolvelist");
         /** @type{Element} */
        this.pplog = goog.dom.getElement("pplog");
         /** @type{Element} */
        this.pphinttime = goog.dom.getElement("pphinttime");

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
                goog.net.XhrIo.send("/admin/hinttimechange", A2020_expect_204, "POST",
                                    admin2020.serializer.serialize({"puzzle_id": puzzle_id,
                                                                    "hint_time": text}));
                goog.dom.getElement("hinttimechange").style.display = "initial";
                goog.dom.getElement("hinttimechangeentry").style.display = "none";
            });

        this.update();
    }

    update() {
        goog.net.XhrIo.send("/admin/js/puzzle/" + puzzle_id, goog.bind(function(e) {
            var code = e.target.getStatus();
            if (code == 200) {
                this.build(e.target.getResponseJson());
            } else {
                alert(e.target.getResponseText());
            }
        }, this));
    }

    /** param{PuzzlePageData} data */
    build(data) {
        this.ppsolvecount.innerHTML = "" + data.solves.length;

        var i, j, el;

        this.pphinttime.innerHTML = admin2020.time_formatter.duration(data.hint_time);

        el = this.ppsolvelist;
        el.innerHTML = "";
        for (i = 0; i < data.solves.length; ++i) {
            var so = data.solves[i];
            if (i > 0) {
                el.appendChild(goog.dom.createDom("BR"));
            }
            el.appendChild(goog.dom.createDom(
                "A", {href: "/admin/team/" + so.username + "/puzzle/" + puzzle_id},
                so.name));
            el.appendChild(goog.dom.createTextNode(" (" + admin2020.time_formatter.duration(so.duration) + ")"));
        }

        A2020_DisplayLog(this.pplog, data.log);

        admin2020.counter.reread();
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

        goog.net.XhrIo.send("/admin/bb/team", goog.bind(function(e) {
            var code = e.target.getStatus();
            if (code != 200) {
                alert(e.target.getResponseText());
            }
            this.update_all_teams(e.target.getResponseJson());
        }, this), "GET");
    }

    /** @param{Object<string, BBTeamData>} data */
    update_all_teams(data) {
        this.team_data = data;
        this.team_els = [];

        for (var i = 0; i < team_list.length; ++i) {
            var username = team_list[i][0];
            var d = this.team_data[username];

            var score = goog.dom.createDom("DIV", "bb-score", "" + d.score);
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

        goog.net.XhrIo.send("/admin/bb/team/" + username, goog.bind(function(e) {
            var code = e.target.getStatus();
            if (code != 200) {
                alert(e.target.getResponseText());
            }
            this.update_one_team(username, e.target.getResponseJson());
        }, this), "GET");
    }

    /** @param{string} username */
    /** @param{BBTeamData} data */
    update_one_team(username, data) {
        var el = this.team_data[username].el;
        this.team_data[username] = data;
        this.team_data[username].el = el;

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

    refresh_taskqueue() {
        goog.net.XhrIo.send("/admin/bb/taskqueue", goog.bind(function(e) {
            var code = e.target.getStatus();
            if (code != 200) {
                alert(e.target.getResponseText());
            }
            this.update_taskqueue(/** @type{BBTaskQueue} */ (e.target.getResponseJson()));
        }, this), "GET");
    }

    /** @param{BBTaskQueue} data */
    update_taskqueue(data) {
        if (!data) return;
        this.taskqueue.innerHTML = "" + data.size + " (" + (data.size - data.claimed) + ")";
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
}

window.onload = function() {
    admin2020.serializer = new goog.json.Serializer();
    admin2020.waiter = new Common_Waiter(
        new A2020_Dispatcher(), "/wait", received_serial, sessionStorage,
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

    if (goog.dom.getElement("user-roles")) {
        admin2020.user_roles = new A2020_UserRoles()
    }

    if (goog.dom.getElement("bbtaskqueue")) {
        admin2020.bigboard = new A2020_BigBoard();
    }

    if (goog.dom.getElement("stwaits")) {
        admin2020.server_page = new A2020_ServerPage();
    }

    if (team_username && !puzzle_id) {
        admin2020.team_page = new A2020_TeamPage();
    }
    if (puzzle_id && !team_username) {
        admin2020.puzzle_page = new A2020_PuzzlePage();
    }
    if (puzzle_id && team_username) {
        admin2020.team_puzzle_page = new A2020_TeamPuzzlePage();
    }
}

