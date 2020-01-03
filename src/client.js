goog.require("goog.dom");
goog.require("goog.dom.classlist");
goog.require("goog.dom.ViewportSizeMonitor");
goog.require("goog.events");
goog.require("goog.events.KeyCodes");
goog.require("goog.style");
goog.require("goog.net.XhrIo");
goog.require("goog.json.Serializer");

class H2020_Dispatcher {
    constructor() {
        /** @type{boolean} */
        this.dirty_activity = false;
        /** @type{boolean} */
        this.dirty_all_puzzles = false;

        this.methods = {
            "history_change": goog.bind(this.history_change, this),
            "solve": goog.bind(this.solve, this),
            "open_land": goog.bind(this.open_land, this),
            "update_start": goog.bind(this.update_start, this),
            "to_page": goog.bind(this.to_page, this),
            "hint_history": goog.bind(this.hint_history, this),
            "update_fastpass": goog.bind(this.update_fastpass, this),
            "receive_fastpass": goog.bind(this.receive_fastpass, this),
            "apply_fastpass": goog.bind(this.apply_fastpass, this),
            "warn_fastpass": goog.bind(this.warn_fastpass, this),
            "hints_open": goog.bind(this.hints_open, this),
            "update_map": goog.bind(this.update_map, this),
            "update_header": goog.bind(this.update_header, this),
            "video": goog.bind(this.video, this),
            "event_complete": goog.bind(this.event_complete, this),
            "segments_complete": goog.bind(this.segments_complete, this),
            "post_erratum": goog.bind(this.post_erratum, this),
            "pennies": goog.bind(this.pennies, this),
            "close_hunt": goog.bind(this.close_hunt, this),
            "preload": goog.bind(this.preload, this),
        }
    }

    pre_dispatch() {
        this.dirty_activity = false;
        this.dirty_all_puzzles = false;
    }
    post_dispatch() {
        if (goog.DEBUG) {
            console.log("dirty activity", this.dirty_activity, "all_puzzles", this.dirty_all_puzzles);
        }
        if (this.dirty_activity && hunt2020.activity) hunt2020.activity.update();
        if (this.dirty_all_puzzles && hunt2020.all_puzzles) hunt2020.all_puzzles.update();
    }

    /** @param{Message} msg */
    dispatch(msg) {
        this.methods[msg.method](msg);
    }

    /** @param{Message} msg */
    preload(msg) {
        var delay = Math.random() * msg.spread * 1000;
        setTimeout(
            function() {
                if (!msg.maps) return;
                for (const url of msg.maps) {
                    var img = new Image();
                    img.src = url;
                }
            }, delay);
    }

    /** @param{Message} msg */
    pennies(msg) {
        if (hunt2020.workshop) hunt2020.workshop.update();
        this.dirty_activity = true;
    }

    /** @param{Message} msg */
    history_change(msg) {
        this.dirty_activity = true;
        if (msg.puzzle_id == puzzle_id) {
            hunt2020.submit_panel.update_history();
        }
    }

    /** @param{Message} msg */
    close_hunt(msg) {
        hunt_closed = true;
        if (hunt2020.submit_panel) {
            hunt2020.submit_panel.close_hunt();
        }
        if (hunt2020.guest_services) {
            hunt2020.guest_services.close_hunt();
        }
        hunt2020.toast_manager.add_toast(msg.text, 30000, null, "salmon", null);
    }

    /** @param{Message} msg */
    post_erratum(msg) {
        hunt2020.toast_manager.add_toast(
            "An erratum has been posted for <b>" + msg.title + "</b>.", 6000, null, "salmon",
            "/errata");
    }

    /** @param{Message} msg */
    hint_history(msg) {
        if (hunt2020.guest_services) {
            hunt2020.guest_services.update_hint_history(msg.puzzle_id);
            hunt2020.guest_services.update_hints_open();
        }
        if (msg.notify) {
            hunt2020.toast_manager.add_toast(
                "Hunt HQ has replied to your hint request on <b>" +
                    msg.title + "</b>.", 6000, null, "salmon",
                "/guest_services?p=" + msg.puzzle_id);
            if (puzzle_id == msg.puzzle_id) {
                var el = goog.dom.getElement("puzzhints");
                if (el) {
                    goog.dom.classlist.add(el, "urgent");
                }
            }
        }
        this.dirty_activity = true;
    }

    /** @param{Message} msg */
    hints_open(msg) {
        if (hunt2020.guest_services) {
            hunt2020.guest_services.update_hints_open();
        }
        if (puzzle_id == msg.puzzle_id) {
            var el = goog.dom.getElement("puzzhints");
            if (el) {
                goog.dom.classlist.remove(el, "hidden");
            }
        }
        if (msg.title) {
            hunt2020.toast_manager.add_toast(
                "You're now eligible to request hints for <b>" + msg.title + "</b>.",
                6000, null, "salmon", "/guest_services?p=" + msg.puzzle_id);
            this.dirty_activity = true;
        }
    }

    /** @param{Message} msg */
    update_header(msg) {
        var buzz = goog.dom.getElement("buzz");
        if (!buzz) return;
        buzz.innerHTML = msg.score;

        var el = goog.dom.getElement("navpass");
        if (msg.passes) {
            el.style.display = "inline";
            el.innerHTML = "";
            var i = msg.passes;
            if (i > 3) i = 3;
            el.appendChild(goog.dom.createDom("A", {id: "ppicon" + i, href: "/guest_services"}));
        } else {
            el.style.display = "none";
        }

        el = goog.dom.getElement("landtags");
        el.innerHTML = "";
        for (var i = 0; i < msg.lands.length; ++i) {
            var a = goog.dom.createDom("A", {className: "landtag",
                                             href: msg.lands[i][2]}, msg.lands[i][0]);
            a.style.position = "relative";
            a.style.backgroundColor = msg.lands[i][1];
            el.appendChild(a);

            var tip = goog.dom.createDom("DIV", "landtip", msg.lands[i][3]);
            a.appendChild(tip);
        }

        if (msg.to_go) {
            var a = goog.dom.createDom("A", {
                id: "nextland",
                className: "landtag"}, "??");
            a.style.position = "relative";
            el.appendChild(a);

            if (msg.to_go) {
                var tip = goog.dom.createDom("DIV", "landtip");
                tip.innerHTML = msg.to_go;
                a.appendChild(tip);
            }
        }

    }

    /** @param{Message} msg */
    video(msg) {
        hunt2020.toast_manager.add_toast(
            "A new Park History video is available!<br><img class=videothumb src=\"" + msg.thumb + "\">",
            6000, false, "blue", "/about_the_park#history");
        if (hunt2020.videos) hunt2020.videos.update();
    }

    /** @param{Message} msg */
    solve(msg) {
        if (msg.audio) {
            hunt2020.audio_manager.start(msg.audio);
        }
        if (msg.video_url) {
            hunt2020.toast_manager.special_toast(msg, 15000);
        } else {
            hunt2020.toast_manager.add_toast(
                "<b>" + msg.title + "</b> was solved!", 6000, true, "blue",
                "/puzzle/" + msg.puzzle_id);
        }

        if (puzzle_id == msg.puzzle_id) {
            var el = goog.dom.getElement("submit");
            if (el) {
                goog.dom.classlist.add(el, "submitsolved");
                el.innerHTML = "Solved";
            }
        }
        this.dirty_activity = true;
        this.dirty_all_puzzles = true;

        if (hunt2020.guest_services) {
            hunt2020.guest_services.update_hint_history(msg.puzzle_id);
            hunt2020.guest_services.update_hints_open();
        }

        if (typeof refresh_puzzle !== 'undefined' && refresh_puzzle) refresh_puzzle();
    }

    /** @param{Message} msg */
    open_land(msg) {
        hunt2020.toast_manager.add_toast(
            "<b>" + msg.title + "</b> is now open!", 6000, null, "blue",
            "/land/" + msg.land);
        this.dirty_activity = true;
        this.dirty_all_puzzles = true;
    }

    /** @param{Message} msg */
    update_fastpass(msg) {
        if (hunt2020.guest_services) hunt2020.guest_services.build_fastpass(msg.fastpass);
    }

    /** @param{Message} msg */
    receive_fastpass(msg) {
        hunt2020.toast_manager.add_toast(
            "You've received a PennyPass!", 6000, null, "blue", "/guest_services");
        if (hunt2020.guest_services) {
            hunt2020.guest_services.build_fastpass(msg.fastpass);
        }
        this.dirty_activity = true;
    }

    /** @param{Message} msg */
    warn_fastpass(msg) {
        hunt2020.toast_manager.add_toast(
            "You have a PennyPass expiring in <b>" + msg.text + "!</b>  Don't miss out!",
            6000, null, "blue", "/guest_services");
    }

    /** @param{Message} msg */
    apply_fastpass(msg) {
        if (msg.land) {
            var text = "A PennyPass has been applied to <b>" + msg.title + "</b>!";
            hunt2020.toast_manager.add_toast(text, 6000, null, "blue", "/land/" + msg.land);
        }
        if (hunt2020.guest_services) {
            hunt2020.guest_services.build_fastpass(msg.fastpass);
        }
        this.dirty_activity = true;
    }

    /** @param{Message} msg */
    update_start(msg) {
        var el = goog.dom.getElement("opencountdown");
        if (el) {
            el.setAttribute("data-until", msg.new_start.toString());
            hunt2020.counter.reread();
        }
    }

    /** @param{Message} msg */
    to_page(msg) {
        window.location = msg.url;
    }

    /** @param{Message} msg */
    update_map(msg) {
        if (hunt2020.map_draw) hunt2020.map_draw.update_map(msg);
        this.dirty_all_puzzles = true;
        this.dirty_activity = true;
    }

    /** @param{Message} msg */
    event_complete(msg) {
        var els = document.querySelectorAll(".eventcomplete");
        if (els && els.length == msg.completed.length) {
            for (var i = 0; i < els.length; ++i) {
                var idx = els[i].id.substr(5);
                if (msg.completed[parseInt(idx, 10)]) {
                    els[i].innerHTML = "Completed";
                } else {
                    els[i].innerHTML = "";
                }
            }
        }
    }

    /** @param{Message} msg */
    segments_complete(msg) {
        if (msg.segments) {
            for (const [s, e] of Object.entries(msg.segments)) {
                var el = goog.dom.getElement("segment_" + s);
                el.innerHTML = "&mdash; " + e.answer;
                el = goog.dom.getElement("instructions_" + s);
                el.innerHTML = e.instructions;
            }
        }
    }
}

/** @param{Action} data */
/** @param{function(Object)} callback */
function H2020_DoAction(data, callback) {
    goog.net.XhrIo.send("/action", callback, "POST",
                        hunt2020.serializer.serialize(data));
}

class H2020_EmojiPicker {
    constructor(parent) {
        /** @type{boolean} */
        this.built = false;
        /** @type{?H2020_SubmitPanel} */
        this.parent = parent;

        /** @type{?Element} */
        this.input = goog.dom.getElement("answer");
        /** @type{?Element} */
        this.emojiinput = goog.dom.getElement("emoji-answer");;
        goog.events.listen(this.emojiinput, goog.events.EventType.KEYDOWN,
            goog.bind(this.onkeydown, this));
        goog.events.listen(this.emojiinput, goog.events.EventType.INPUT,
                           goog.bind(this.oninput, this));
        goog.events.listen(this.emojiinput, goog.events.EventType.PASTE,
                           goog.bind(this.onpaste, this));

        goog.events.listen(this.emojiinput, goog.events.EventType.DRAGOVER,
                           e => e.preventDefault());
        goog.events.listen(this.emojiinput, goog.events.EventType.DROP,
                           e => e.preventDefault());

        /** @type{?Element} */
        this.pickerbutton = goog.dom.getElement("emoji-picker-button");
        goog.events.listen(this.pickerbutton, goog.events.EventType.CLICK,
            goog.bind(this.toggle, this));

        /** @type{?Element} */
        this.emojipicker = null;
        /** @type{?Element} */
        this.searchinput = null;
        /** @type{?Element} */
        this.pickerbody = null;
    }

    build() {
        this.emojipicker = goog.dom.getElement("emoji-picker");
        this.searchinput = goog.dom.getElement("emoji-picker-search-input");
        this.pickerbody = goog.dom.getElement("emoji-picker-body");

        goog.events.listen(goog.dom.getDocument(), goog.events.EventType.CLICK,
            goog.bind(this.onclick, this));

        goog.events.listen(this.searchinput, goog.events.EventType.INPUT,
            goog.bind(this.filter_emojis, this));

        var vsm = new goog.dom.ViewportSizeMonitor();
        goog.events.listen(vsm, goog.events.EventType.RESIZE, goog.bind(this.resize, this));

        this.built = true;
    }

    onkeydown(event) {
        if (event.keyCode == goog.events.KeyCodes.ENTER) {
          this.parent.submit();
          event.preventDefault();
        } else if (event.keyCode != goog.events.KeyCodes.BACKSPACE &&
                   this.input.value.length >= this.max_input_length()) {
          event.preventDefault();
        }
    }

    oninput(event) {
        var text = event.target.innerHTML;
        var children = goog.dom.getChildren(event.target);
        for (var i = 0; i < children.length; ++i) {
          if (children[i].alt) {
            text = text.replace(goog.dom.getOuterHtml(children[i]), children[i].alt);
          }
        }
        this.input.value = this.sanitize_input(text, this.max_input_length());
    }

    onpaste(event) {
        event.preventDefault();
        event.stopPropagation();
        var text = event.getBrowserEvent().clipboardData.getData("text/plain");
        text = this.sanitize_input(text, this.max_input_length() - this.input.value.length);
        document.execCommand("insertText", false, text);
        twemoji.parse(this.emojiinput);
    }

    sanitize_input(text, maxlength) {
      if (text) {
        text = text.replace(/[\r\n]+/gm, "");
        text = text.substring(0, maxlength);
      }
      return text;
    }

    max_input_length() {
        return this.input.getAttribute("maxlength");
    }

    onclick(event) {
        var isEmojiPickerElement = function(node) {
            return node.id == "emoji-picker" || node.id == "emoji-picker-button";
        };
        if (!goog.dom.getAncestor(event.target, isEmojiPickerElement, true)) {
            this.close();
        } else {
            var isEmojiNode = function(node) {
              return node.classList && node.classList.contains("emojisprite");
            };
            var emojiNode = goog.dom.getAncestor(event.target, isEmojiNode, true);
            if (emojiNode) {
                this.pick_emoji(emojiNode);
            }
        }
    }

    filter_emojis() {
        var searchQuery = this.searchinput.value.toLowerCase();
        // Hide all the groups.
        var groups = goog.dom.getElementsByClass("emoji-picker-group");
        for (var i = 0; i < groups.length; ++i) {
            goog.style.setElementShown(groups[i], false);
        }
        var emojis = goog.dom.getElementsByClass("emoji-picker-emoji");
        for (var i = 0; i < emojis.length; ++i) {
            var show = emojis[i].getAttribute("data-search").includes(searchQuery);
            goog.style.setElementShown(emojis[i], show);
            // Show any group containing a matching emoji.
            if (show) {
                goog.style.setElementShown(goog.dom.getParentElement(emojis[i]), true);
            }
        }
    }

    pick_emoji(emojiNode) {
        if (this.input.value.length >= this.max_input_length()) {
          return;
        }
        var text = emojiNode.getAttribute("data-text");
        var x = emojiNode.getAttribute("data-x");
        var y = emojiNode.getAttribute("data-y");
        x = parseInt(x, 10);
        y = parseInt(y, 10);
        if (text) {
            goog.dom.append(/** @type{!Node} */ (this.emojiinput),
                            goog.dom.createDom(
                                "IMG", {className: "emojisprite",
                                        draggable: false,
                                        alt: text,
                                        src: "data:image/png;base64,R0lGODlhFAAUAIAAAP///wAAACH5BAEAAAAALAAAAAAUABQAAAIRhI+py+0Po5y02ouz3rz7rxUAOw==",
                                        style: "background-position: -" + (x*20) + "px -" +
                                        (y*20) + "px;"}));
            this.input.value += text;
        }
    }

    clear_input() {
        if (!this.built) this.build();
        this.emojiinput.innerHTML = "";
    }

    resize() {
        if (!this.built) this.build();
        var inputSize = goog.style.getBorderBoxSize(this.emojiinput);
        var inputPos = goog.style.getPosition(this.emojiinput);
        goog.style.setPosition(this.emojipicker, inputPos.x, inputPos.y + inputSize.height);
        goog.style.setWidth(this.emojipicker, inputSize.width);
    }

    reset_search() {
        if (!this.built) this.build();
        this.searchinput.value = "";
        this.filter_emojis();
        this.pickerbody.scrollTop = 0;
    }

    focus_search_input() {
        this.searchinput.focus();
    }

    toggle() {
        if (!this.built) this.build();
        if (goog.dom.classlist.contains(this.emojipicker, "active")) {
            this.close();
        } else {
            this.resize();
            this.reset_search();
            this.show();
        }
    }

    show() {
        if (!this.built) this.build();
        goog.dom.classlist.add(this.emojipicker, "active");
        // focus on search input field, once fade-in is complete.
        setTimeout(goog.bind(this.focus_search_input, this), 200);
    }

    close() {
        goog.dom.classlist.remove(this.emojipicker, "active");
    }
}

class H2020_SubmitPanel {
    constructor() {
        /** @type{boolean} */
        this.built = false;

        /** @type{?Element} */
        this.submitpanel = null;
        /** @type{?Element} */
        this.input = null;
        /** @type{?Element} */
        this.table = null;
        /** @type{?Element} */
        this.top_note = null;
        /** @type{?Element} */
        this.entry = null;
        /** @type{H2020_EmojiPicker|null} */
        this.emoji_picker = null;

        /** @type{boolean} */
        this.has_overlay = false;

        /** @type{Element} */
        this.errata = goog.dom.getElement("errata");

        this.build();
    }

    build() {
        if (hunt_closed) {
            this.close_hunt();
        }

        this.submitpanel = goog.dom.getElement("submitpanel");
        this.input = goog.dom.getElement("answer");
        this.table = goog.dom.getElement("submit_table_body");
        this.top_note = goog.dom.getElement("top_note");
        this.entry = goog.dom.getElement("submitentry");
        goog.events.listen(this.input, goog.events.EventType.KEYDOWN,
                           goog.bind(this.onkeydown, this));
        goog.events.listen(this.input, goog.events.EventType.DRAGOVER,
                           e => e.preventDefault());
        goog.events.listen(this.input, goog.events.EventType.DROP,
                           e => e.preventDefault());

        if (goog.dom.getElement("emoji-picker-button")) {
          this.emoji_picker = new H2020_EmojiPicker(this);
        }

        var b = goog.dom.getElement("submitsubmit");
        goog.events.listen(b, goog.events.EventType.CLICK, goog.bind(this.submit, this));

        this.built = true;
        this.update_history();
    }

    update_history() {
        if (!this.built) return;
        if (this.submitpanel.style == "none") return;
        goog.net.XhrIo.send("/js/submit/" + puzzle_id,
                            Common_invoke_with_json(this, this.render_history));
    }

    /** @param{SubmissionHistory} response */
    render_history(response) {
        if (response.total) {
            var t = response.total;
            var c = response.correct;
            if (t == 1) {
                this.top_note.innerHTML = "This puzzle has a single answer.";
            } else {
                this.top_note.innerHTML = "This puzzle has " + t + " answers.  " +
                (t == c ? "You have found them all!" :
                 (c > 0 ? "You have found " + c + " so far.  " : "") +
                 "Submit each answer separately.");
            }
            this.top_note.style.display = "initial";
        } else {
            this.top_note.style.display = "none";
        }

        this.table.innerHTML = "";

        if (response.history.length == 0) {
            this.table.appendChild(
                goog.dom.createDom("TR", null,
                                   goog.dom.createDom("TD", {className: "submit-empty", colSpan: 3},
                                                      "Nothing submitted yet.")));
        }

        var cancelsub = function(sub) {
            return function() {
                H2020_DoAction({action: "cancel_submit",
                                puzzle_id: puzzle_id,
                                submit_id: sub.submit_id}, Common_expect_204);
            };
        };

        var tr = null;
        for (var i = 0; i < response.history.length; ++i) {
            var sub = response.history[i];
            var el = null;
            if (sub.state == "pending") {
                el = goog.dom.createDom("SPAN", {className: "counter submit-timer"});
                el.setAttribute("data-until", sub.check_time)
            }

            var answer = null;
            var time_el = null;
            if (sub.state == "pending") {
                var link = goog.dom.createDom("A", {className: "submit-cancel"}, "cancel");
                goog.events.listen(link, goog.events.EventType.CLICK, cancelsub(sub));
                answer = sub.answer;
                time_el = [link, el];
            } else {
                answer = sub.answer;
                time_el = hunt2020.time_formatter.format(sub.submit_time);
            }


            tr = goog.dom.createDom(
                "TR", {className: "submit-" + sub.color},
                goog.dom.createDom("TD", {className: "submit-answer"},
                                   answer),
                goog.dom.createDom("TD", {className: "submit-time"}, time_el),
                goog.dom.createDom("TD", {className: "submit-state"},
                                   goog.dom.createDom("SPAN", null,
                                                      sub.state)));
            if (typeof twemoji !== 'undefined') {
              tr = twemoji.parse(tr);
            }
            this.table.appendChild(tr);

            if (sub.response) {
                var td = goog.dom.createDom("TD", {colSpan: 3});
                td.innerHTML = sub.response;
                tr = goog.dom.createDom("TR", {className: "submit-extra submit-" + sub.color}, td);
                this.table.appendChild(tr);
            }
        }

        hunt2020.counter.reread();

        this.table.scrollTop = this.table.scrollHeight + 100;

        if (response.allowed) {
            this.entry.style.visibility = "visible";
        } else {
            this.entry.style.visibility = "hidden";
        }

        if (response.errata) {
            if (goog.DEBUG) {
                console.log(response);
            }
            this.errata.style.display = "block";
            this.errata.innerHTML = "";
            for (const e of response.errata) {
                var p = goog.dom.createElement("P");
                p.innerHTML = "<b>Erratum posted " + hunt2020.time_formatter.format(e.when) + ":</b> " + e.text;
                this.errata.appendChild(p);
            }
        }
    }

    submit() {
        if (hunt_closed) return;
        var answer = this.input.value;
        if (answer == "") return;
        this.input.value = "";
        if (this.emoji_picker) {
          this.emoji_picker.clear_input();
        }
        H2020_DoAction(
            {action: "submit", puzzle_id: puzzle_id, answer: answer},
            function(e) {
                var code = e.target.getStatus();
                if (code == 409) {
                    var text = e.target.getResponseText();
                    text = twemoji.parse(text);
                    if (text) {
                        hunt2020.toast_manager.add_toast("You've already submitted <b>" + text + "</b>.",
                                                         5000, null, "salmon");
                    } else {
                        hunt2020.toast_manager.add_toast("Invalid submission.", 5000, null, "salmon");
                    }
                } else if (code != 204) {
                    if (goog.DEBUG) {
                        alert(e.target.getResponseText());
                    }
                }
            });
    }

    onkeydown(e) {
        if (e.keyCode == goog.events.KeyCodes.ENTER) {
            this.submit();
            e.preventDefault();
        } else if (e.keyCode == goog.events.KeyCodes.ESC) {
            this.close();
            e.preventDefault();
        }
    }

    toggle() {
        if (!this.built) this.build();
        if (goog.dom.classlist.contains(this.submitpanel, "panel-visible")) {
            this.close();
        } else {
            this.show();
        }
    }

    show() {
        goog.dom.classlist.addRemove(this.submitpanel, "panel-invisible",
                                     "panel-visible");
        this.update_history();
        // focus on input field, once slide-out animation is complete.
        setTimeout(goog.bind(this.focus_input, this), 200);
        return false;
    }

    focus_input() {
        this.input.focus();
    }

    close() {
        goog.dom.classlist.addRemove(this.submitpanel, "panel-visible",
                                     "panel-invisible");
    }

    close_hunt() {
        console.log("panel closing hunt");
        var el = goog.dom.getElement("submit");
        if (el) {
            el.innerHTML = "closed";
        }
        el = goog.dom.getElement("submitsubmit");
        if (el) {
            el.disabled = true;
        }
    }
}

class H2020_ToastManager {
    constructor() {
        /** @type{Element} */
        this.toasts_div = goog.dom.createDom("DIV", {className: "toasts"});
        document.body.appendChild(this.toasts_div);

        /** @type{number} */
        this.toasts = 0;
        /** @type{Array<Element>} */
        this.dead_toasts = [];

        /** @type{number} */
        this.serial = 0;
    }

    add_toast(message, timeout, audio, color="blue", click_to="") {
        this.serial += 1;
        var tt = goog.dom.createDom("DIV");
        tt.innerHTML = message;

        var icon = null;
        if (audio) {
            icon = goog.dom.createDom(
                "IMG",
                {src: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg==",
                 className: localStorage.getItem("mute") ? "mute" : "mute muteoff"});

            goog.events.listen(icon, goog.events.EventType.CLICK,
                               goog.bind(hunt2020.audio_manager.toggle_mute, hunt2020.audio_manager));
        }

        var t = goog.dom.createDom("DIV", {className: "toast toast"+color}, icon, tt);

        this.toasts += 1;
        this.toasts_div.appendChild(t);
        setTimeout(goog.bind(this.expire_toast, this, t), timeout);

        if (click_to) {
            tt.style.cursor = "pointer";
            goog.events.listen(tt, goog.events.EventType.CLICK, function(e) {
                window.location = click_to;
            });
        }
    }

    special_toast(msg, timeout) {
        this.serial += 1;
        var img = goog.dom.createDom("IMG", {src: msg.url});
        var over = goog.dom.createDom("IMG", {src: msg.video_url});

        var p = goog.dom.createDom("P");
        p.innerHTML = msg.text;
        var div = goog.dom.createDom("DIV", null, img, over);
        div.style.width = "600px";
        div.style.height = "481px";

        var inner = goog.dom.createDom("DIV", "specialtoast toastblue", p, div);

        var outer = goog.dom.createDom("DIV", "specialtoasts", inner);

        this.toasts += 1;
        this.toasts_div.appendChild(outer);
        setTimeout(goog.bind(this.expire_special, this, outer), timeout);

        if (msg.to_go) {
            inner.style.cursor = "pointer";
            goog.events.listen(inner, goog.events.EventType.CLICK, function(e) {
                window.location = msg.to_go;
                e.stopPropagation();
            });
        }
        goog.events.listen(outer, goog.events.EventType.CLICK,
                           goog.bind(this.expire_special, this, outer));
    }

    expire_special(t) {
        goog.dom.classlist.add(t, "specialhidden");
        setTimeout(t => {
            goog.dom.removeNode(t);
        }, 600);
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

class H2020_MapDraw {
    constructor() {
        if (typeof event_hash === 'undefined') {
            return;
        }

        /** @type{Element} */
        this.map_el = goog.dom.getElement("map");
        /** @type{Element} */
        this.mapmap_el = goog.dom.getElement("mapmap");
        /** @type{Element} */
        this.list_el = goog.dom.getElement("maplist");

        /** @type{?Element} */
        this.highlight_el = null;
        /** @type{?Element} */
        this.mask_el = null;

        /** @type{?string} */
        this.land_name = null;
        /** @type{?string} */
        this.icon_name = null;

        if (event_hash) {
            var eh = localStorage.getItem("event_hash");
            if (eh != event_hash) {
                localStorage.clear();
                localStorage.setItem("event_hash", event_hash);
            }
        }

        if (goog.DEBUG) {
            this.map_el.tabIndex = 0;
            goog.events.listen(this.map_el, goog.events.EventType.KEYDOWN,
                               goog.bind(this.onkeydown, this));
        }

        var mapdata = /** @type{MapData} */ (initial_json);
        this.shortname = mapdata.shortname;

        if (window.performance.navigation.type == 2) {
            this.update();
        } else {
            this.draw_map(mapdata);
        }
    }

    onkeydown(e) {
        if (!goog.DEBUG) return;
        var d = 1;
        if (e.shiftKey) d = 10;
        if (e.keyCode == goog.events.KeyCodes.UP) {
            H2020_DoAction({action: "adjust_offset", land: this.land_name, icon: this.icon_name,
                            dy: -d}, Common_expect_204);
            e.preventDefault();
        } else if (e.keyCode == goog.events.KeyCodes.DOWN) {
            H2020_DoAction({action: "adjust_offset", land: this.land_name, icon: this.icon_name,
                            dy: d}, Common_expect_204);
            e.preventDefault();
        } else if (e.keyCode == goog.events.KeyCodes.RIGHT) {
            if (e.ctrlKey) {
                H2020_DoAction({action: "adjust_offset", land: this.land_name, icon: this.icon_name,
                                dw: d}, Common_expect_204);
            } else {
                H2020_DoAction({action: "adjust_offset", land: this.land_name, icon: this.icon_name,
                                dx: d}, Common_expect_204);
            }
            e.preventDefault();
        } else if (e.keyCode == goog.events.KeyCodes.LEFT) {
            if (e.ctrlKey) {
                H2020_DoAction({action: "adjust_offset", land: this.land_name, icon: this.icon_name,
                                dw: -d}, Common_expect_204);
            } else {
                H2020_DoAction({action: "adjust_offset", land: this.land_name, icon: this.icon_name,
                                dx: -d}, Common_expect_204);
            }
            e.preventDefault();
        }
    }

    update_map(msg) {
        for (var i = 0; i < msg.maps.length; ++i) {
            if (msg.maps[i] == this.shortname) {
                this.update();
                break;
            }
        }
    }

    update() {
        goog.net.XhrIo.send("/js/map/" + this.shortname,
                            Common_invoke_with_json(this, this.draw_map));
    }

    draw_map(mapdata) {
        if (this.shortname != mapdata.shortname) return;

        this.land_name = mapdata.shortname;

        this.map_el.innerHTML = "";
        this.mapmap_el.innerHTML = "";
        this.list_el.innerHTML = "";

        if (mapdata.base_url) {
            var el = goog.dom.createDom("IMG", {src: mapdata.base_url,
                                                className: "base",
                                                useMap: "#mapmap"});
            this.map_el.style.width = "" + mapdata.width + "px";
            this.map_el.style.height = "" + mapdata.height + "px";
            this.map_el.appendChild(el);

        }

        for (var i = 0; i < mapdata.items.length; ++i) {
            this.draw_item(mapdata.items[i]);
        }
        hunt2020.counter.reread();
    }

    draw_item(it) {
        if (it.icon_url) {
            var mask_el = null;
            if (it.mask_url) {
                mask_el = goog.dom.createDom("IMG", {
                    src: it.mask_url, className: "mask"});
                mask_el.style.left = "" + it.xywh[0] + "px";
                mask_el.style.top = "" + it.xywh[1] + "px";
                this.map_el.appendChild(mask_el);
            }

            var k;
            if (it.solved || typeof it.solved === 'undefined') {
                k = "icon";
            } else {
                k = "icon blurred";
            }
            var el = goog.dom.createDom("IMG", {
                src: it.icon_url, className: k});
            el.style.left = "" + it.xywh[0] + "px";
            el.style.top = "" + it.xywh[1] + "px";
            this.map_el.appendChild(el);

            if (it.poly && it.special) {
                var area = goog.dom.createDom("AREA", {shape: "poly",
                                                       coords: it.poly});
                if (it.url) area.href = it.url;
                this.mapmap_el.appendChild(area);

                goog.events.listen(area, goog.events.EventType.MOUSEENTER,
                                   goog.bind(this.special_item_enter, this, it));
                goog.events.listen(area, goog.events.EventType.MOUSELEAVE,
                                   goog.bind(this.item_leave, this, it));
            } else if (it.poly) {
                var area = goog.dom.createDom("AREA", {shape: "poly",
                                                       coords: it.poly});
                if (it.url) area.href = it.url;
                this.mapmap_el.appendChild(area);

                goog.events.listen(area, goog.events.EventType.MOUSEENTER,
                                   goog.bind(this.item_enter, this, it, mask_el));
                goog.events.listen(area, goog.events.EventType.MOUSELEAVE,
                                   goog.bind(this.item_leave, this, it));
            }

            if (!it.solved && it.name) {
                this.add_title(it);
            }
        }

        if (it.name && !it.nolist) {
            var a = [];
            if (it.new_open) {
                var sp = goog.dom.createDom("SPAN", {className: "newopen counter"}, "NEW");
                sp.setAttribute("data-expires", it.new_open);
                a.push(sp);
            }
            a.push(goog.dom.createDom("A", {href: it.url}, it.name));
            if (it.answer) {
                a.push(" \u2014 ");
                var aa = goog.dom.createDom("SPAN", {className: it.solved ? "solved" : "unsolved"},
                                            it.answer);
                if (typeof twemoji !== 'undefined') {
                    aa = twemoji.parse(aa);
                }
                a.push(aa);
            }
            el = goog.dom.createDom("LI", it.spaceafter ? "spaceafter" : null, a);
            this.list_el.appendChild(el);
        }
    }

    special_item_enter(it) {
        var hel = goog.dom.createDom("DIV");
        hel.style.left = "" + it.special.xywh[0] + "px";
        hel.style.top = "" + it.special.xywh[1] + "px";
        this.highlight_el = hel;
        this.map_el.appendChild(hel);

        var el = goog.dom.createDom("IMG", {
            src: it.special.icon_url, className: "icon"});
        el.style.left = "" + it.special.xywh[0] + "px";
        el.style.top = "" + it.special.xywh[1] + "px";
        hel.appendChild(el);

        if (it.special.name) {
            var h = goog.dom.createDom("DIV", {className: "psign"});
            h.innerHTML = it.special.name;
            h.style.left = "" + it.special.xywh[0] + "px";
            h.style.top = "" + it.special.xywh[1] + "px";
            h.style.width = "" + it.special.xywh[2] + "px";
            h.style.height = "" + it.special.xywh[3] + "px";
            hel.appendChild(h);
        }
    }

    item_enter(it, mask_el) {
        this.item_leave(null);

        if (mask_el) {
            mask_el.style.display = "inline";
            this.mask_el = mask_el;
        }

        if (it.answer) {
            this.highlight_el  = this.add_title(it);
        }

        this.icon_name = it.icon;
    }

    add_title(it) {
        var ch = [it.name];
        if (it.answer) {
            var a = goog.dom.createDom("B", null, goog.dom.createTextNode(it.answer));
            if (typeof twemoji !== 'undefined') {
                a = twemoji.parse(a);
            }
            ch.push(a);
        }

        var h = goog.dom.createDom("DIV", {className: "p"}, ch);
        h.style.left = "" + (it.xywh[0] + it.offset[0]) + "px";
        h.style.top = "" + (it.xywh[1] + it.offset[1]) + "px";
        h.style.width = "" + (it.xywh[2] + it.offset[2]) + "px";
        h.style.height = "" + it.xywh[3] + "px";

        this.map_el.appendChild(h);
        return h;
    }

    item_leave(it) {
        if (this.mask_el) {
            this.mask_el.style.display = "none";
            this.mask_el = null;
        }
        if (this.highlight_el) {
            goog.dom.removeNode(this.highlight_el);
            this.highlight_el = null;
        }
        this.icon_name = null;
    }
}

class H2020_AudioManager {
    constructor() {
        this.current = null;
        this.current_url = null;
        /** @type{?number} */
        this.current_request_time = null;
        window.addEventListener("storage", goog.bind(this.mute_changed, this));
    }

    start(url) {
        if (this.current && !this.current.ended) {
            // previous audio still playing, skip this one
            return;
        }
        if (!this.current || url != this.current_url) {
            this.current = new Audio(url);
            this.current_url = url;
        }
        if (localStorage.getItem("mute")) {
            this.current.muted = true;
        }
        this.current_request_time = (new Date()).getTime();
        var promise = this.current.play();
        if (promise !== undefined) {
            promise.then(goog.bind(this.start_playback, this))
                .catch(error => {
                    console.log("playback error", error);
                });
        }
    }

    start_playback() {
        var delay = (new Date()).getTime() - this.current_request_time;
        if (delay > 1000) {
            console.log("cancelling sound; too late");
            this.current.pause();
        }
        if (goog.DEBUG) {
            console.log("playback has started after", delay, "ms");
        }
    }

    toggle_mute() {
        if (localStorage.getItem("mute")) {
            // Turn muting off.
            localStorage.removeItem("mute");
            this.mute_changed();
            return false;
        } else {
            // Turn muting on
            localStorage.setItem("mute", "1");
            this.mute_changed();
            return true;
        }
    }

    mute_changed() {
        var els = document.querySelectorAll(".mute");
        var el = goog.dom.getElement("mutebox");

        if (localStorage.getItem("mute")) {
            if (this.current) this.current.muted = true;
            for (var i = 0; i < els.length; ++i) {
                els[i].className = "mute";
            }
            if (el) el.checked = false;
        } else {
            if (this.current) this.current.muted = false;
            for (var i = 0; i < els.length; ++i) {
                els[i].className = "mute muteoff";
            }
            if (el) el.checked = true;
        }

    }
}

class H2020_GuestServices {
    constructor() {
        /** @type{?string} */
        this.sel_shortname = null;
        /** @type{?Element} */
        this.sel_div = null;

        /** @type{Element} */
        this.use_button = goog.dom.getElement("fpuse");
        goog.events.listen(this.use_button, goog.events.EventType.CLICK,
                           goog.bind(this.use, this));

        this.build_fastpass((/** @type{GuestServicesData} */ (initial_json)).fastpass);

        /** @type{Element} */
        this.hintcurr = goog.dom.getElement("hintcurr");
        /** @type{Element} */
        this.hintnone = goog.dom.getElement("hintnone");
        /** @type{Element} */
        this.hintsome = goog.dom.getElement("hintsome");
        /** @type{Element} */
        this.hintselect = goog.dom.getElement("hintselect");
        /** @type{Element} */
        this.hintcancel = goog.dom.getElement("hintcancel");

        goog.events.listen(
            this.hintcancel, goog.events.EventType.CLICK,
            function(e) {
                H2020_DoAction({action: "cancel_hint"}, Common_expect_204);
            });

        goog.events.listen(this.hintselect, goog.events.EventType.CHANGE,
                           goog.bind(this.select_puzzle, this));

        /** @type{?string} */
        this.hint_selected = null;
        /** @type{string} */
        this.hint_displayed = "";
        /** @type{?string} */
        this.restricted_to = null;

        /** @type{Element} */
        this.textarea = goog.dom.getElement("hinttext");
        /** @type{Element} */
        this.history = goog.dom.getElement("hinthistory");

        /** @type{Element} */
        this.hintrequest = goog.dom.getElement("hintrequest");

        /** @type{Object<string, boolean>} */
        this.solved = {};

        goog.events.listen(this.hintrequest, goog.events.EventType.CLICK,
                           goog.bind(this.submit, this));

        /** @type{Element} */
        this.mutebox = goog.dom.getElement("mutebox");
        if (this.mutebox) {
            if (localStorage.getItem("mute")) {
                this.mutebox.checked = false;
            } else {
                this.mutebox.checked = true;
            }
            goog.events.listen(this.mutebox, goog.events.EventType.CHANGE,
                               goog.bind(hunt2020.audio_manager.toggle_mute, hunt2020.audio_manager));
        }

        /** @type{Element} */
        this.newphone = goog.dom.getElement("newphone");

        if (hunt_closed) {
            this.close_hunt();
        }

        goog.events.listen(goog.dom.getElement("newphonesubmit"), goog.events.EventType.CLICK,
                           goog.bind(this.update_phone, this));

        if (window.performance.navigation.type == 2) {
            this.update_hints_open();
        } else {
            this.build_hints((/** @type{GuestServicesData} */ (initial_json)).hints);
        }
    }

    close_hunt() {
        this.hintcancel.disabled = true;
        this.hintrequest.disabled = true;
    }

    update_phone() {
        var value = this.newphone.value;
        if (value == "") return;
        H2020_DoAction({action: "update_phone", phone: value},
                       Common_invoke_with_json(this, this.phone_updated));
    }

    phone_updated() {
        goog.dom.getElement("newphonesaved").style.display = "inline";
    }

    update_hints_open() {
        goog.net.XhrIo.send("/js/hintsopen", Common_invoke_with_json(this, this.build_hints));
    }

    select_puzzle(e) {
        var old = this.hint_selected;
        this.hint_selected = this.hintselect.options[this.hintselect.selectedIndex].value;
        if (old != this.hint_selected) {
            this.textarea.value = "";
        }
        this.hintselect.style.color = "black";
        this.update_hint_history(this.hint_selected);
    }

    update_hint_history(puzzle_id) {
        if (puzzle_id == this.hint_selected) {
            goog.net.XhrIo.send("/js/hints/" + this.hint_selected,
                                Common_invoke_with_json(this, this.render_hint_history));
        }
    }

    /** @param{HintHistory} data */
    render_hint_history(data) {
        goog.dom.getElement("hintui").style.display = "block";

        this.hint_displayed = data.puzzle_id;
        localStorage.setItem("lh_" + data.puzzle_id, "" + data.history.length);

        var ht = goog.dom.getElement("hinttext");
        if (data.history.length == 0) {
            this.history.innerHTML = "<span id=hintnotyet>You have not requested any hints on this puzzle.</span>";
            ht.setAttribute(
                "placeholder",
                "Describe what you've tried, where you're stuck\u2026");
            ht.setAttribute("rows", "9");
            this.hintrequest.innerHTML = "Send request";
        } else {
            ht.setAttribute(
                "placeholder",
                "Add a followup\u2026");
            ht.setAttribute("rows", "3");
            this.hintrequest.innerHTML = "Send followup";
            this.history.innerHTML = "";
            var dl = goog.dom.createDom("DL");
            for (var i = 0; i < data.history.length; ++i) {
                var msg = data.history[i];
                var dt = goog.dom.createDom(
                    "DT", null,
                    "At " + hunt2020.time_formatter.format(msg.when) + ", " + msg.sender + " wrote:");

                var dd = goog.dom.createDom("DD", msg.special ? "special" : null);
                if (msg.special) {
                    if (msg.special == "cancel") {
                        dd.innerHTML = "(request canceled by team)";
                    } else if (msg.special == "solved") {
                        dd.innerHTML = "(request canceled due to solving puzzle)";
                    }
                } else {
                    dd.innerHTML = msg.text;
                }
                dl.appendChild(dt);
                dl.appendChild(dd);
            }
            this.history.appendChild(dl);
        }

        this.update_send_button();
    }

    submit() {
        if (hunt_closed) return;
        var text = this.textarea.value;
        if (text == "") return;
        this.textarea.value = "";
        H2020_DoAction({action: "hint_request",
                        puzzle_id: this.hint_selected,
                        text: text}, Common_expect_204);
        this.hintrequest.blur();
    }

    /** @param{OpenHints} data */
    build_hints(data) {
        this.restricted_to = data.current;
        this.solved = {};
        if (data.available.length > 0) {
            this.hintnone.style.display = "none";
            this.hintsome.style.display = "block";

            var target = this.hint_selected;
            if (!target) {
                target = puzzle_id;
            }
            var target_found = false;

            this.hintselect.innerHTML = "";
            if (!this.hint_selected) {
                this.hintselect.appendChild(
                    goog.dom.createDom("OPTION", {selected: true,
                                                  disabled: true,
                                                  hidden: true},
                                       "\u2014 select \u2014"));
                this.hintselect.style.color = "#999";
            }
            var curr_title = null;
            for (var i = 0; i < data.available.length; ++i) {
                var it = data.available[i];
                if (data.current == it[0]) {
                    curr_title = it[1];
                }
                var d = {value: it[0]};
                if (it[0] == target) {
                    d["selected"] = true;
                    target_found = true;
                }
                this.hintselect.appendChild(
                    goog.dom.createDom("OPTION", d, it[1] + (it[2] ? " [solved]" : "")));
                if (it[2]) {
                    this.solved[it[0]] = true;
                }
            }

            if (target_found) {
                this.select_puzzle(target);
            }

            if (curr_title) {
                this.hintcurr.style.display = "block";
                this.hintcurr.innerHTML = "Waiting for reply on: <b>" + curr_title + "</b>";
                this.hintcancel.style.display = "inline";
            } else {
                this.hintcurr.style.display = "none";
                this.hintcancel.style.display = "none";
            }
        } else {
            // No hints available.
            this.hintnone.style.display = "block";
            this.hintsome.style.display = "none";
        }

        this.update_send_button();
    }

    update_send_button() {
        if (this.solved[this.hint_displayed]) {
            this.hintrequest.disabled = true;
            this.hintrequest.innerHTML = "Puzzle solved";
        } else if (this.restricted_to && this.restricted_to != this.hint_displayed) {
            this.hintrequest.disabled = true;
            this.hintrequest.innerHTML = "Waiting for reply";
        } else {
            this.hintrequest.disabled = false;
            this.hintrequest.innerHTML = "Send request";
        }
        if (hunt_closed) {
            this.hintrequest.disabled = true;
        }
    }

    /** @param{FastPassState} data */
    build_fastpass(data) {
        var e_none = goog.dom.getElement("fphavenone");
        var e_some = goog.dom.getElement("fphavesome");
        if (data.expire_time.length == 0) {
            e_none.style.display = "initial";
            e_some.style.display = "none";
            return;
        }
        e_none.style.display = "none";
        e_some.style.display = "initial";

        var fppasses = goog.dom.getElement("fppasses");
        fppasses.innerHTML = "";

        var fpone = goog.dom.getElement("fpone");
        var fpsome = goog.dom.getElement("fpsome");
        if (data.expire_time.length == 1) {
            fpone.style.display = "block";
            fpsome.style.display = "none";
        } else {
            fpone.style.display = "none";
            fpsome.style.display = "block";
        }

        for (var i = 0; i < data.expire_time.length; ++i) {
            if (i >= 6) {
                var more = data.expire_time.length - 6;
                if (more > 0) {
                    var s = goog.dom.createDom("SPAN", null, "(plus " + more + " more\u2026)");
                    fppasses.appendChild(s);
                }
                break;
            }

            var s = goog.dom.createDom("SPAN", {className: "counter"});
            s.setAttribute("data-until", data.expire_time[i].toString());
            var d = goog.dom.createDom("DIV", "pennypass", s);
            fppasses.appendChild(d);
        }
        hunt2020.counter.reread();

        e_none = goog.dom.getElement("fpunusable");
        e_some = goog.dom.getElement("fpusable");
        if (data.usable_lands.length == 0) {
            e_none.style.display = "initial";
            e_some.style.display = "none";
            return;
        }
        e_none.style.display = "none";
        e_some.style.display = "initial";

        var e_icons = goog.dom.getElement("fpicons");
        e_icons.innerHTML = "";
        this.sel_div = null;
        for (var i = 0; i < data.usable_lands.length; ++i) {
            var u = data.usable_lands[i];
            var d = goog.dom.createDom("DIV", "fpselect");
            if (u.url) {
                d.appendChild(goog.dom.createDom("IMG", {className: "fpicon",
                                                         src: u.url}));
            }
            d.appendChild(goog.dom.createDom("DIV", {className: "fptitle"}, u.title));
            e_icons.appendChild(d);

            if (u.shortname == this.sel_shortname) {
                goog.dom.classlist.add(d, "fpselected");
                this.sel_div = d;
            }

            goog.events.listen(d, goog.events.EventType.CLICK,
                               goog.bind(this.selectland, this, d, u.shortname));
        }
        if (this.sel_div) {
            this.use_button.disabled = false;
        } else {
            this.sel_shortname = null;
            this.use_button.disabled = true;
        }
    }

    selectland(div, shortname) {
        if (this.sel_div) {
            goog.dom.classlist.remove(this.sel_div, "fpselected");
        }
        if (this.sel_shortname == shortname) {
            this.sel_div = null;
            this.sel_shortname = null;
            this.use_button.disabled = true;
            return;
        }
        this.sel_div = div;
        this.sel_shortname = shortname;
        this.use_button.disabled = false;
        goog.dom.classlist.add(div, "fpselected");
    }

    use() {
        if (!this.sel_shortname) return;
        H2020_DoAction({action: "apply_pennypass",
                        land: this.sel_shortname}, Common_expect_204);
        goog.dom.classlist.remove(this.sel_div, "fpselected");
        this.sel_div = null;
        this.sel_shortname = null;
    }
}


var hunt2020 = {
    serializer: null,
    waiter: null,
    submit_panel: null,
    hint_panel: null,
    time_formatter: null,
    toast_manager: null,
    audio_manager: null,
    map_draw: null,
    counter: null,
    guest_services: null,
    activity: null,
    videos: null,
    all_puzzles: null,
    errata: null,
    workshop: null,
}

/** @param{Node} e */
/** @param{Event} ev */
function emoji_builder(e, ev) {
    var t0 = performance.now();
    var xhr = /** @type{goog.net.XhrIo} */ (ev.target);
    var obj = xhr.getResponseJson();
    for (var i = 0; i < obj.length; ++i) {
        var group = obj[i][0];
        var emojis = obj[i][1];

        var ch = new Array();

        var gr = goog.dom.createDom("DIV", {className: "emoji-picker-group"});
        ch.push(goog.dom.createDom("DIV", {className: "emoji-picker-group-title"}, group));

        for (var j = 0; j < emojis.length; ++j) {
            var em = emojis[j];
            var title = em[0].split("|", 1)[0];
            var text = em[1];
            var x = em[2];
            var y = em[3];
            var d = goog.dom.createDom(
                "DIV", {className: "emojisprite",
                        style: "background-position: -" + (x*28) + "px -" +
                        (y*28) + "px"});
            d.setAttribute("data-text", text);
            d.setAttribute("data-x", x);
            d.setAttribute("data-y", y);
            var s = goog.dom.createDom(
                "SPAN", {className: "emoji-picker-emoji", title: title}, d);
            s.setAttribute("data-search", em[0]);
            ch.push(s);
        }
        goog.dom.append(gr, ch);
        goog.dom.append(/** @type{!Node} */ (e), gr);
    }
    var t1 = performance.now();
}

function refresh_header(dispatcher) {
    goog.net.XhrIo.send("/js/header",
                        Common_invoke_with_json(dispatcher, dispatcher.update_header));
}

window.onload = function() {
    if (typeof hunt_closed === 'undefined') {
        hunt_closed = false;
    }

    hunt2020.serializer = new goog.json.Serializer();
    hunt2020.time_formatter = new Common_TimeFormatter();
    hunt2020.counter = new Common_Counter(hunt2020.time_formatter);

    hunt2020.toast_manager = new H2020_ToastManager();
    hunt2020.audio_manager = new H2020_AudioManager();

    var dispatcher = new H2020_Dispatcher();

    if (window.performance.navigation.type == 2) {
        hunt2020.nav_back = true;
        refresh_header(dispatcher);
    } else if (initial_header) {
        dispatcher.update_header(initial_header);
    }

    hunt2020.waiter = new Common_Waiter(
        dispatcher, "/wait", received_serial, sessionStorage,
        function(text) {
            hunt2020.toast_manager.add_toast(text, 36000000, null, "salmon", "/");
        });
    hunt2020.waiter.start();

    // PuzzlePage             a
    // EventsPage             b
    // WorkshopPage           c
    // LandMapPage            d
    // PlayerHomePage         e
    // ActivityLogPage        f
    // AboutTheParkPage       g
    // GuestServicesPage      i
    // AllPuzzlesPage         j
    // ErrataPage             k
    // WorkshopPage           l
    // HealthAndSafetyPage    m
    // SponsorPage            n
    // RunaroundPage          o

    // Pages with SUBMIT buttons.
    if (page_class == "a" || page_class == "b" || page_class == "l" || page_class == "o") {
        var a = goog.dom.getElement("submit");
        hunt2020.submit_panel = new H2020_SubmitPanel();
        goog.events.listen(a, goog.events.EventType.CLICK,
                           goog.bind(hunt2020.submit_panel.toggle, hunt2020.submit_panel));

        var e = goog.dom.getElement("emoji-picker-body");
        if (e) {
            goog.net.XhrIo.send(edb, goog.bind(emoji_builder, null, e));
        }

        if (typeof last_hint !== "undefined" && last_hint) {
            var x = localStorage.getItem("lh_" + puzzle_id);
            if (x) {
                x = parseInt(x, 10);
            } else {
                x = 0;
            }
            if (x < last_hint) {
                var el = goog.dom.getElement("puzzhints");
                if (el) {
                    goog.dom.classlist.add(el, "urgent");
                }
            }
        }
    }

    if (puzzle_id && puzzle_init) puzzle_init();

    // Pages that draw maps (lands, home page)
    if (page_class == "d" || page_class == "e") {
        hunt2020.map_draw = new H2020_MapDraw();
    }

    if (page_class == "f") hunt2020.activity = new H2020_ActivityLog();
    if (page_class == "g") hunt2020.videos = new H2020_Videos();
    if (page_class == "i") hunt2020.guest_services = new H2020_GuestServices();
    if (page_class == "j") hunt2020.all_puzzles = new H2020_AllPuzzles();
    if (page_class == "k") hunt2020.errata = new H2020_Errata();
    if (page_class == "l") hunt2020.workshop = new H2020_Workshop();
}

class H2020_ActivityLog {
    constructor() {
        /** @type{Element} */
        this.log = goog.dom.getElement("log");

        this.update();
    }

    update() {
        goog.net.XhrIo.send("/js/log", Common_invoke_with_json(this, this.build));
    }

    /** param{ActivityLogData} data */
    build(data) {
        if (data.log.length == 0) {
            this.log.innerHTML = "No activity.";
            return;
        }
        this.log.innerHTML = "";
        for (var i = 0; i < data.log.length; ++i) {
            var e = data.log[i];
            var td = goog.dom.createDom("TD");
            for (var j = 0; j < e.htmls.length; ++j) {
                if (j > 0) td.appendChild(goog.dom.createDom("BR"));
                var sp = goog.dom.createDom("SPAN");
                sp.innerHTML = e.htmls[j];
                td.appendChild(sp);
            }
            var tr = goog.dom.createDom("TR",
                                        null,
                                        goog.dom.createDom("TH", null, hunt2020.time_formatter.format(e.when)),
                                        td);
            this.log.appendChild(tr);
        }
    }
}

class H2020_Videos {
    constructor() {
        /** @type{Element} */
        this.video_div = goog.dom.getElement("videolist");
        this.update();
    }

    update() {
        goog.net.XhrIo.send("/js/videos", Common_invoke_with_json(this, this.build));
    }

    /** param{Array<Video>} data */
    build(data) {
        if (data.length == 0) {
            this.video_div.innerHTML = "No videos available yet.";
            return;
        }
        this.video_div.innerHTML = "";
        for (var i = 0; i < data.length; ++i) {
            var el = goog.dom.createDom("H3", null, "Video " + (i+1));
            this.video_div.appendChild(el);
            el = goog.dom.createDom("VIDEO", {className: "storyvideo",
                                                controls: true,
                                                preload: "none",
                                                poster: data[i].poster},
              goog.dom.createDom("SOURCE", {src: data[i].video}));
            this.video_div.appendChild(el);
        }
    }
}

class H2020_Errata {
    constructor() {
        this.build(initial_json);
    }

    /** param{Array<Erratum>} data */
    build(data) {
        var dl = goog.dom.getElement("erlist");
        dl.innerHTML = "";
        for (var i = 0; i < data.length; ++i) {
            var e = data[i];

            var dt = goog.dom.createDom(
                "DT", null,
                goog.dom.createDom("A", {href: e.url}, e.title),
                " (posted " + hunt2020.time_formatter.format(e.when) + ")");
            var dd = goog.dom.createDom("DD", null);
            dd.innerHTML = e.text;
            dl.appendChild(dt);
            dl.appendChild(dd);
        }
    }
}

class H2020_AllPuzzles {
    constructor() {
        this.loplist = goog.dom.getElement("loplist");
        this.update();
    }

    update() {
        goog.net.XhrIo.send("/js/puzzles", Common_invoke_with_json(this, this.build));
    }

    /** param{AllPuzzles} data */
    build(data) {
        this.loplist.innerHTML = "";
        for (var i = 0; i < data.lands.length; ++i) {
            var land = data.lands[i];
            var ul = goog.dom.createDom("UL");
            var a = goog.dom.createDom("A", {href: land.url}, land.title);
            var li = goog.dom.createDom("LI", "lopland", a, ul);
            for (var j = 0; j < land.puzzles.length; ++j) {
                var p = land.puzzles[j];
                a = goog.dom.createDom("A", {href: p.url}, p.title);
                var lili = goog.dom.createDom("LI", "loppuzzle", a);
                if (p.spacebefore) {
                    goog.dom.classlist.add(lili, "spacebefore")
                }
                if (p.answer) {
                    lili.appendChild(goog.dom.createTextNode(" \u2014 "));
                    lili.appendChild(goog.dom.createDom("SPAN", "solved", p.answer));
                }

                ul.appendChild(lili);
            }
            this.loplist.appendChild(li);
        }
        twemoji.parse(this.loplist);
    }
}

class H2020_Workshop {
    constructor() {
        /** @type{Element} */
        this.wsearned = goog.dom.getElement("wsearned");
        /** @type{Element} */
        this.wsearnednames = goog.dom.getElement("wsearnednames");
        /** @type{Element} */
        this.wscoll = goog.dom.getElement("wscoll");
        /** @type{Element} */
        this.wscollnames = goog.dom.getElement("wscollnames");
        /** @type{Element} */
        this.submit = goog.dom.getElement("submit");
        this.update();
    }

    update() {
        goog.net.XhrIo.send("/js/workshop", Common_invoke_with_json(this, this.build));
    }

    /** param{WorkshopData} data */
    build(data) {
        if (!this.wsearned) return;

        var e = data.earned;
        if (e.length == 0) {
            this.wsearned.style.display = "none";
        } else {
            this.wsearned.style.display = "block";

            if (e.length == 1) {
                this.wsearnednames.innerHTML = "<b>" + e[0] + "</b> penny";
            } else if (e.length == 2) {
                this.wsearnednames.innerHTML = "<b>" + e[0] + "</b> and <b>" + e[1] + "</b> pennies";
            } else {
                var out = [];
                for (var i = 0; i < e.length-1; ++i) {
                    out.push("<b>" + e[i] + "</b>, ");
                }
                out.push(" and <b>" + e[e.length-1] + "</b> pennies");
                this.wsearnednames.innerHTML = out.join("");
            }
        }

        var c = data.collected;
        if (c.length == 0) {
            this.wscoll.style.display = "none";
        } else {
            this.wscoll.style.display = "block";

            this.wscollnames.innerHTML = "";
            for (var i = 0; i < c.length; ++i) {
                this.wscollnames.appendChild(goog.dom.createDom("LI", null, c[i]));
            }
        }

        if (data.allow_submit) {
            this.submit.style.display = "block";
        } else {
            this.submit.style.display = "none";
        }
    }
}

