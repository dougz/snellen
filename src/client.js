goog.require("goog.dom");
goog.require("goog.dom.classlist");
goog.require("goog.dom.ViewportSizeMonitor");
goog.require("goog.events");
goog.require("goog.events.KeyCodes");
goog.require("goog.style");
goog.require("goog.net.XhrIo");
goog.require("goog.ui.ModalPopup");
goog.require("goog.json.Serializer");

class H2020_Dispatcher {
    constructor() {
        this.methods = {
            "history_change": goog.bind(this.history_change, this),
            "solve": goog.bind(this.solve, this),
            "open": goog.bind(this.open, this),
            "achieve": goog.bind(this.achieve, this),
            "update_start": goog.bind(this.update_start, this),
            "to_page": goog.bind(this.to_page, this),
            "hint_history": goog.bind(this.hint_history, this),
            "receive_fastpass": goog.bind(this.receive_fastpass, this),
            "apply_fastpass": goog.bind(this.apply_fastpass, this),
            "warn_fastpass": goog.bind(this.warn_fastpass, this),
            "hints_open": goog.bind(this.hints_open, this),
            "update_map": goog.bind(this.update_map, this),
            "update_header": goog.bind(this.update_header, this),
            "video": goog.bind(this.video, this),
            "event_complete": goog.bind(this.event_complete, this),
        }
    }

    /** @param{Message} msg */
    dispatch(msg) {
        this.methods[msg.method](msg);
    }

    /** @param{Message} msg */
    history_change(msg) {
        if (msg.puzzle_id == puzzle_id) {
            hunt2020.submit_panel.update_history();
        }
    }

    /** @param{Message} msg */
    hint_history(msg) {
        if (hunt2020.guest_services) {
            hunt2020.guest_services.update_hint_history();
            hunt2020.guest_services.update_hints_open();
        }
        if (msg.notify) {
            hunt2020.toast_manager.add_toast(
                "Hunt HQ has replied to your hint request on <b>" +
                    msg.title + "</b>.", 6000, null, "salmon",
                "/guest_services?p=" + msg.puzzle_id);
        }
        if (hunt2020.activity) hunt2020.activity.update();
    }

    /** @param{Message} msg */
    hints_open(msg) {
        if (hunt2020.guest_services) {
            hunt2020.guest_services.update_hints_open();
        }
        if (msg.title) {
            hunt2020.toast_manager.add_toast(
                "You're now eligible to request hints for <b>" + msg.title + "</b>.",
                6000, null, "salmon", "/guest_services?p=" + msg.puzzle_id);
            if (hunt2020.activity) hunt2020.activity.update();
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

            var tip = goog.dom.createDom("DIV", "landtip");
            tip.innerHTML = "Generate " + msg.to_go + " to unlock the next land!";
            a.appendChild(tip);
        }

    }

    /** @param{Message} msg */
    video(msg) {
        hunt2020.toast_manager.add_toast(
            "A new video is available!<br><img class=videothumb src=\"" + msg.thumb + "\">",
            6000, false, "blue", "/videos");
        if (hunt2020.videos) hunt2020.videos.update();
    }

    /** @param{Message} msg */
    solve(msg) {
        if (msg.audio) {
            hunt2020.audio_manager.start(msg.audio);
        }
        hunt2020.toast_manager.add_toast(
            "<b>" + msg.title + "</b> was solved!", 6000, true, "blue", "/puzzle/" + msg.puzzle_id);

        if (puzzle_id == msg.puzzle_id) {
            var el = goog.dom.getElement("submit");
            if (el) {
                goog.dom.classlist.add(el, "submitsolved");
                el.innerHTML = "Solved";
            }
        }
        if (hunt2020.activity) hunt2020.activity.update();
        if (hunt2020.all_puzzles) hunt2020.all_puzzles.update();
    }

    /** @param{Message} msg */
    open(msg) {
        hunt2020.toast_manager.add_toast(
            "<b>" + msg.title + "</b> is now open!", 6000, null, "blue",
            "/land/" + msg.land);
        if (hunt2020.activity) hunt2020.activity.update();
        if (hunt2020.guest_services) hunt2020.guest_services.build_fastpass(msg.fastpass);
        if (hunt2020.all_puzzles) hunt2020.all_puzzles.update();
    }

    /** @param{Message} msg */
    achieve(msg) {
        hunt2020.toast_manager.add_toast(
            "You received the <b>" + msg.title + "</b> pin!", 6000, null, "gold", "/pins");
        if (hunt2020.activity) hunt2020.activity.update();
        if (hunt2020.achievements) hunt2020.achievements.update();
    }

    /** @param{Message} msg */
    receive_fastpass(msg) {
        hunt2020.toast_manager.add_toast(
            "You've received a PennyPass!", 6000, null, "blue", "/guest_services");
        if (hunt2020.guest_services) {
            hunt2020.guest_services.build_fastpass(msg.fastpass);
        }
        if (hunt2020.activity) hunt2020.activity.update();
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
        if (hunt2020.activity) hunt2020.activity.update();
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
        if (hunt2020.map_draw) {
            hunt2020.map_draw.update_map(msg);
        }
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
        this.input.value = this.sanitize_input(text, this.max_input_length());;
    }

    onpaste(event) {
        event.preventDefault();
        event.stopPropagation();
        var text = event.getBrowserEvent().clipboardData.getData("text/plain");
        text = this.sanitize_input(text, this.max_input_length() - this.input.value.length);
        if (typeof twemoji !== 'undefined') {
          text = twemoji.parse(text);
        }
        document.execCommand("insertHTML", false, text);
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
            var show = emojis[i].title.includes(searchQuery);
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
        /** @type{Object|null} */
        this.serializer = null;

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

        this.cancel = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"><path d="M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm5 13.59L15.59 17 12 13.41 8.41 17 7 15.59 10.59 12 7 8.41 8.41 7 12 10.59 15.59 7 17 8.41 13.41 12 17 15.59z"/><path d="M0 0h24v24H0z" fill="none"/></svg>';
    }

    build() {
        this.serializer = new goog.json.Serializer();

        this.submitpanel = goog.dom.getElement("submitpanel");
        this.input = goog.dom.getElement("answer");
        this.table = goog.dom.getElement("submit_table_body");
        this.top_note = goog.dom.getElement("top_note");
        this.entry = goog.dom.getElement("submitentry");
        goog.events.listen(this.input, goog.events.EventType.KEYDOWN, goog.bind(this.onkeydown, this));

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
        goog.net.XhrIo.send("/submit_history/" + puzzle_id,
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
                goog.net.XhrIo.send("/submit_cancel/" + puzzle_id + "/" + sub.submit_id,
                                    Common_expect_204);
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
                var link = goog.dom.createDom("A", {className: "submit-cancel"});
                link.innerHTML = this.cancel;
                goog.events.listen(link, goog.events.EventType.CLICK, cancelsub(sub));
                answer = sub.answer;
                time_el = [link, el];
            } else {
                answer = sub.answer;
                time_el = hunt2020.time_formatter.format(sub.submit_time);
            }


            tr = goog.dom.createDom(
                "TR", {className: "submit-" + sub.state},
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
                tr = goog.dom.createDom("TR", {className: "submit-extra"}, td);
                this.table.appendChild(tr);
            }
        }

        hunt2020.counter.reread();

        var t = goog.dom.getElement("submit_table_scroll");
        t.scrollTop = t.scrollHeight;

        if (response.allowed) {
            this.entry.style.visibility = "visible";
        } else {
            this.entry.style.visibility = "hidden";
        }
    }

    submit() {
        var answer = this.input.value;
        if (answer == "") return;
        this.input.value = "";
        if (this.emoji_picker) {
          this.emoji_picker.clear_input();
        }
        goog.net.XhrIo.send("/submit", function(e) {
            var code = e.target.getStatus();
            if (code == 409) {
                var text = e.target.getResponseText();
                if (typeof twemoji !== 'undefined') {
                  text = twemoji.parse(text);
                }
                hunt2020.toast_manager.add_toast("You've already submitted <b>" + text + "</b>.",
                                                 5000, null, "salmon");
            } else if (code != 204) {
                alert(e.target.getResponseText());
            }
        }, "POST", this.serializer.serialize({"puzzle_id": puzzle_id, "answer": answer}));
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
        if (!this.built) this.build();
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

        var mapdata = /** @type{MapData} */ (initial_json);
        this.shortname = mapdata.shortname;

        this.draw_map(mapdata);
    }

    update_map(msg) {
        for (var i = 0; i < msg.maps.length; ++i) {
            if (msg.maps[i] == this.shortname) {
                goog.net.XhrIo.send("/js/map/" + this.shortname,
                                    Common_invoke_with_json(this, this.draw_map));
                break;
            }
        }
    }

    draw_map(mapdata) {
        if (this.shortname != mapdata.shortname) return;

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

            var el = goog.dom.createDom("IMG", {
                src: it.icon_url, className: "icon"});
            el.style.left = "" + it.xywh[0] + "px";
            el.style.top = "" + it.xywh[1] + "px";
            this.map_el.appendChild(el);

            if (it.poly && it.name) {
                var area = goog.dom.createDom("AREA", {shape: "poly",
                                                       coords: it.poly});
                if (it.url) area.href = it.url;
                this.mapmap_el.appendChild(area);

                goog.events.listen(area, goog.events.EventType.MOUSEENTER,
                                   goog.bind(this.item_enter, this, it, mask_el));
                goog.events.listen(area, goog.events.EventType.MOUSELEAVE,
                                   goog.bind(this.item_leave, this, it));
            } else if (it.poly && it.special) {
                var area = goog.dom.createDom("AREA", {shape: "poly",
                                                       coords: it.poly});
                if (it.url) area.href = it.url;
                this.mapmap_el.appendChild(area);

                goog.events.listen(area, goog.events.EventType.MOUSEENTER,
                                   goog.bind(this.special_item_enter, this, it));
                goog.events.listen(area, goog.events.EventType.MOUSELEAVE,
                                   goog.bind(this.item_leave, this, it));
            }

            if (!it.solved && it.name) {
                this.add_title(it);
            }
        }

        if (it.name) {
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

        var h = goog.dom.createDom("DIV", {className: "psign"});
        h.innerHTML = it.special.name;
        h.style.left = "" + it.special.xywh[0] + "px";
        h.style.top = "" + it.special.xywh[1] + "px";
        h.style.width = "" + it.special.xywh[2] + "px";
        h.style.height = "" + it.special.xywh[3] + "px";
        hel.appendChild(h);
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
        h.style.left = "" + it.xywh[0] + "px";
        h.style.top = "" + it.xywh[1] + "px";
        h.style.width = "" + it.xywh[2] + "px";
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
    }
}

class H2020_AudioManager {
    constructor() {
        this.current = null;
        this.current_url = null;
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
        var promise = this.current.play();
        if (promise !== undefined) {
            promise.catch(error => {});
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

        if (localStorage.getItem("mute")) {
            if (this.current) this.current.muted = true;
            for (var i = 0; i < els.length; ++i) {
                els[i].className = "mute";
            }
        } else {
            if (this.current) this.current.muted = false;
            for (var i = 0; i < els.length; ++i) {
                els[i].className = "mute muteoff";
            }
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

        goog.events.listen(this.hintselect, goog.events.EventType.CHANGE,
                           goog.bind(this.select_puzzle, this));

        /** @type{?string} */
        this.hint_selected = null;
        /** @type{?string} */
        this.hint_displayed = null;
        /** @type{?string} */
        this.restricted_to = null;

        this.serializer = new goog.json.Serializer();
        /** @type{Element} */
        this.textarea = goog.dom.getElement("hinttext");
        /** @type{Element} */
        this.history = goog.dom.getElement("hinthistory");

        /** @type{Element} */
        this.hintrequest = goog.dom.getElement("hintrequest");

        goog.events.listen(this.hintrequest, goog.events.EventType.CLICK,
                           goog.bind(this.submit, this));

        this.build_hints((/** @type{GuestServicesData} */ (initial_json)).hints);
    }

    update_hints_open() {
        goog.net.XhrIo.send("/js/hintsopen", Common_invoke_with_json(this, this.build_hints));
    }

    select_puzzle(e) {
        this.hint_selected = this.hintselect.options[this.hintselect.selectedIndex].value;
        this.hintselect.style.color = "black";
        this.update_hint_history();
    }

    update_hint_history() {
        goog.net.XhrIo.send("/hinthistory/" + this.hint_selected,
                            Common_invoke_with_json(this, this.render_hint_history));
    }

    /** @param{HintHistory} data */
    render_hint_history(data) {
        goog.dom.getElement("hintui").style.display = "block";

        this.hint_displayed = data.puzzle_id;

        var ht = goog.dom.getElement("hinttext");
        if (data.history.length == 0) {
            this.history.innerHTML = "<span id=hintnotyet>You have not requested any hints on this puzzle.</span>";
            ht.setAttribute(
                "placeholder",
                "Describe what you've tried, where you're stuck\u2026");
            ht.setAttribute("rows", "9");
        } else {
            ht.setAttribute(
                "placeholder",
                "Add a followup\u2026");
            ht.setAttribute("rows", "3");
            this.history.innerHTML = "";
            var dl = goog.dom.createDom("DL");
            for (var i = 0; i < data.history.length; ++i) {
                var msg = data.history[i];
                var dt = goog.dom.createDom(
                    "DT", null,
                    "At " + hunt2020.time_formatter.format(msg.when) + ", " + msg.sender + " wrote:");
                var dd = goog.dom.createDom("DD", null);
                dd.innerHTML = msg.text;
                dl.appendChild(dt);
                dl.appendChild(dd);
            }
            this.history.appendChild(dl);
        }

        this.update_send_button();
    }

    submit() {
        var text = this.textarea.value;
        if (text == "") return;
        this.textarea.value = "";
        goog.net.XhrIo.send("/hintrequest", Common_expect_204,
                            "POST", this.serializer.serialize({"puzzle_id": this.hint_selected,
                                                               "text": text}));
    }

    /** @param{OpenHints} data */
    build_hints(data) {
        this.restricted_to = data.current;
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
                    goog.dom.createDom("OPTION", d, it[1]));
            }

            if (target_found) {
                this.select_puzzle(target);
            }

            if (curr_title) {
                this.hintcurr.style.display = "block";
                this.hintcurr.innerHTML = "Waiting for reply on: <b>" + curr_title + "</b>";
            } else {
                this.hintcurr.style.display = "none";
            }
        } else {
            // No hints available.
            this.hintnone.style.display = "block";
            this.hintsome.style.display = "none";
        }

        this.update_send_button();
    }

    update_send_button() {
        if (this.restricted_to && this.restricted_to != this.hint_displayed) {
            this.hintrequest.disabled = true;
        } else {
            this.hintrequest.disabled = false;
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
        goog.net.XhrIo.send("/pennypass/" + this.sel_shortname, Common_expect_204);
        goog.dom.classlist.remove(this.sel_div, "fpselected");
        this.sel_div = null;
        this.sel_shortname = null;
    }
}


var hunt2020 = {
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
    achievements: null,
    videos: null,
    all_puzzles: null,
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
            var title = em[0];
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
            ch.push(goog.dom.createDom(
                "SPAN", {className: "emoji-picker-emoji", title: title}, d));
        }
        goog.dom.append(gr, ch);
        goog.dom.append(/** @type{!Node} */ (e), gr);
    }
    var t1 = performance.now();
    console.log("building picker took " + (t1-t0) + " ms");
}


window.onload = function() {
    console.log("page init");

    goog.events.listen(window, goog.events.EventType.PAGESHOW,
                       function(e) { console.log("pageshow", e.type, window.performance.navigation.type, e); });

    hunt2020.time_formatter = new Common_TimeFormatter();
    hunt2020.counter = new Common_Counter(hunt2020.time_formatter);

    hunt2020.toast_manager = new H2020_ToastManager();
    hunt2020.audio_manager = new H2020_AudioManager();

    var dispatcher = new H2020_Dispatcher();
    hunt2020.waiter = new Common_Waiter(
        dispatcher, "/wait", received_serial, sessionStorage,
        function(text) {
            hunt2020.toast_manager.add_toast(text, 36000000, null, "salmon", "/");
        });
    hunt2020.waiter.start();

    // Present on the puzzle pages and the events page.
    var a = goog.dom.getElement("submit");
    if (a) {
        hunt2020.submit_panel = new H2020_SubmitPanel();
        goog.events.listen(a, goog.events.EventType.CLICK,
                           goog.bind(hunt2020.submit_panel.toggle, hunt2020.submit_panel));

        var e = goog.dom.getElement("emoji-picker-body");
        if (e) {
            goog.net.XhrIo.send(edb, goog.bind(emoji_builder, null, e));
        }
    }

    if (puzzle_id && puzzle_init) puzzle_init();

    // Only present on the map pages.
    var m = goog.dom.getElement("map");
    if (m) {
        hunt2020.map_draw = new H2020_MapDraw();
    }

    // Only present on the activity log page.
    if (goog.dom.getElement("log")) {
        hunt2020.activity = new H2020_ActivityLog();
    }

    // Only present on the activity log page.
    if (goog.dom.getElement("videolist")) {
        hunt2020.videos = new H2020_Videos();
    }

    // Only present on the achievements page.
    if (goog.dom.getElement("pins")) {
        hunt2020.achievements = new H2020_Achievements();
    }

    // Only present on the guest services page.
    if (goog.dom.getElement("fphavenone")) {
        hunt2020.guest_services = new H2020_GuestServices();
    }

    if (goog.dom.getElement("loplist")) {
        hunt2020.all_puzzles = new H2020_AllPuzzles();
    }

    if (initial_header) {
        dispatcher.update_header(initial_header);
    }
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

    /** param{Array<string>} data */
    build(data) {
        if (data.length == 0) {
            this.video_div.innerHTML = "No videos available yet.";
            return;
        }
        this.video_div.innerHTML = "";
        for (var i = 0; i < data.length; ++i) {
            var el = goog.dom.createDom("VIDEO", {className: "storyvideo",
                                                  controls: true},
                                        goog.dom.createDom("SOURCE", {src: data[i]}));
            this.video_div.appendChild(el);
        }
    }
}

class H2020_Achievements {
    constructor() {
        this.update();
    }

    update() {
        goog.net.XhrIo.send("/js/pins", Common_invoke_with_json(this, this.build));
    }

    /** param{Array<Achievement>} data */
    build(data) {
        for (var i = 0; i < data.length; ++i) {
            var e = data[i];
            var el = goog.dom.getElement("ach_" + e.name);
            if (!el) continue;
            goog.dom.classlist.addRemove(el, "no", "yes");
            goog.dom.getElement("achsub_" + e.name).innerHTML = e.subtitle;
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

