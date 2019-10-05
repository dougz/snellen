goog.require("goog.dom");
goog.require("goog.dom.classlist");
goog.require("goog.dom.ViewportSizeMonitor");
goog.require("goog.events");
goog.require("goog.events.KeyCodes");
goog.require("goog.style");
goog.require("goog.net.XhrIo");
goog.require("goog.ui.ModalPopup");
goog.require("goog.json.Serializer");
goog.require("goog.i18n.DateTimeFormat");

class H2020_Waiter {
    constructor(dispatcher) {
        /** @type{goog.net.XhrIo} */
        this.xhr = new goog.net.XhrIo();
        /** @type{number} */
        this.serial = received_serial;

        var e = sessionStorage.getItem("serial");
        if (e) {
            e = parseInt(e, 10);
            if (e > this.serial) {
                this.serial = e;
            }
        }

        /** @type{number} */
        this.backoff = 250;
        /** @type(H2020_Dispatcher) */
        this.dispatcher = dispatcher;
    }

    waitcomplete() {
        if (this.xhr.getStatus() == 401) {
            hunt2020.toast_manager.add_toast(
                "Server connection lost.  Please reload to continue.",
                3600000, null, "salmon");
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

        sessionStorage.setItem("serial", this.serial.toString());

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

class H2020_Dispatcher {
    constructor() {
        this.methods = {
            "history_change": this.history_change,
            "solve": this.solve,
            "open": this.open,
            "achieve": this.achieve,
            "update_start": this.update_start,
            "to_page": this.to_page,
            "hint_history": this.hint_history,
            "receive_fastpass": this.receive_fastpass,
            "apply_fastpass": this.apply_fastpass,
            "hints_open": this.hints_open,
            "update_map": this.update_map,
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
        if (msg.puzzle_id == puzzle_id) {
            hunt2020.hint_panel.update_history();
        }
        if (msg.notify) {
            hunt2020.toast_manager.add_toast(
                "Hunt HQ has replied to your hint request on <b>" +
                    msg.title + "</b>.", 6000, null, "salmon");
        }
    }

    /** @param{Message} msg */
    hints_open(msg) {
        if (msg.puzzle_id == puzzle_id) {
            var el = goog.dom.getElement("hinttoggle");
            if (el) {
                el.style.display = "inline";
                hunt2020.toast_manager.add_toast(
                    "You're now eligible to request hints for <b>" + msg.title + ".",
                    6000, null, "salmon");
            }
        }
    }

    /** @param{Message} msg */
    solve(msg) {
        if (msg.audio) {
            hunt2020.audio_manager.start(msg.audio);
        }
        hunt2020.toast_manager.add_toast(
            "<b>" + msg.title + "</b> was solved!", 6000, true);

        if (msg.score) {
            goog.dom.getElement("score").innerHTML = "" + msg.score;
        }

        if (puzzle_id == msg.puzzle_id) {
            var el = goog.dom.getElement("submit");
            if (el) {
                goog.dom.classlist.add(el, "submitsolved");
                el.innerHTML = "Solved";
            }
        }
    }

    /** @param{Message} msg */
    open(msg) {
        hunt2020.toast_manager.add_toast(
            "<b>" + msg.title + "</b> is now open!", 6000);
    }

    /** @param{Message} msg */
    achieve(msg) {
        hunt2020.toast_manager.add_toast(
            "You received the <b>" + msg.title + "</b> pin!", 6000, null, "gold");
    }

    /** @param{Message} msg */
    receive_fastpass(msg) {
        hunt2020.toast_manager.add_toast(
            "You've received a FastPass!", 6000, null);
        if (hunt2020.fastpass) {
            hunt2020.fastpass.build(msg.fastpass);
        }
    }

    /** @param{Message} msg */
    apply_fastpass(msg) {
        var text;
        if (msg.title) {
            text = "A FastPass has been applied to <b>" + msg.land +
                "</b>, opening <b>" + msg.title + "</b>!";
        } else {
            text = "A FastPass has been applied to <b>" + msg.land + "</b>!";
        }
        hunt2020.toast_manager.add_toast(text, 6000, null);
        if (hunt2020.fastpass) {
            hunt2020.fastpass.build(msg.fastpass);
        }
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
            hunt2020.map_draw.draw_map(msg.mapdata);
        }
    }
}

class H2020_TimeFormatter {
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
        var min = Math.trunc(s/60);
        var sec = Math.trunc(s%60);
        return "" + min + ":" + (""+sec).padStart(2, "0");
    }
}

class H2020_EmojiPicker {
    constructor(parent) {
        /** @type{boolean} */
        this.built = false;
        /** @type{?Element} */
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
        goog.net.XhrIo.send("/submit_history/" + puzzle_id, goog.bind(function(e) {
            var code = e.target.getStatus();
            if (code == 200) {
                var response = /** @type{SubmissionHistory} */ (e.target.getResponseJson());
                this.render_history(response);
                if (response.allowed) {
                    this.entry.style.display = "flex";
                } else {
                    this.entry.style.display = "none";
                }
            }
        }, this));
    }

    /** @param{SubmissionHistory} response */
    render_history(response) {
        if (response.total) {
            this.top_note.innerHTML = response.correct + "/" + response.total + " correct answers found";
            this.top_note.style.display = "inline";
        } else {
            this.top_note.style.display = "none";
        }

        this.table.innerHTML = "";

        if (response.history.length == 0) {
            this.table.appendChild(
                goog.dom.createDom("TR", null,
                                   goog.dom.createDom("TD", {className: "submit-empty", colSpan: 3},
                                                      "No submissions for this puzzle.")));
        }

        var cancelsub = function(sub) {
            return function() {
                goog.net.XhrIo.send("/submit_cancel/" + puzzle_id + "/" + sub.submit_id);
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

        if (response.overlay && !this.has_overlay) {
            // actually the div containing the icon images
            var thumb = goog.dom.getElement("thumb");

            var el = goog.dom.createDom("IMG", {
                src: response.overlay,
                className: "icon"});
            thumb.appendChild(el);

            this.add_sparkle(thumb, response.width, response.height);
        }

        var t = goog.dom.getElement("submit_table_scroll");
        t.scrollTop = t.scrollHeight;
    }

    add_sparkle(parent, width, height) {
        var div = goog.dom.createDom("DIV", {className: "icon"});
        div.style.width = "" + width + "px";
        div.style.height = "" + height + "px";

        var star = '<path class="star" d="M0 -1L.5877 .809 -.9511 -.309 .9511 -.309 -.5877 .809Z" />';
        var fivestar = star;
        for (var i = 1; i < 5; ++i) {
            fivestar += `<g transform="rotate(${i*72})">` + star + "</g>";
        }
        var scale = Math.min(width, height) * 0.4;

        var html = `<svg width="${width}" height="${height}">` +
            `<g transform="translate(${width/2},${height/2}) scale(${scale})" fill="yellow">` +
            fivestar + '<g transform="scale(0.5) rotate(36)">' + fivestar +
            "</g></g></svg>";
        div.innerHTML = html;

        parent.appendChild(div);
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

class H2020_HintPanel {
    constructor() {
        /** @type{boolean} */
        this.built = false;
        /** @type{Object|null} */
        this.serializer = null;

        /** @type{Element|null} */
        this.hintpanel = null;

        /** @type{Element|null} */
        this.textarea = null;

        /** @type{Element|null} */
        this.history = null;
    }

    build() {
        this.serializer = new goog.json.Serializer();
        this.hintpanel = goog.dom.getElement("hintpanel");
        this.textarea = goog.dom.getElement("hinttext");
        this.history = goog.dom.getElement("hinthistory");

        var b = goog.dom.getElement("hintrequest");
        goog.events.listen(b, goog.events.EventType.CLICK, goog.bind(this.submit, this));

        this.built = true;
    }

    submit() {
        var text = this.textarea.value;
        if (text == "") return;
        this.textarea.value = "";
        goog.net.XhrIo.send("/hintrequest", function(e) {
            var code = e.target.getStatus();
            if (code != 204) {
                alert(e.target.getResponseText());
            }
        }, "POST", this.serializer.serialize({"puzzle_id": puzzle_id, "text": text}));
    }

    update_history() {
        if (!this.built) return;
        if (this.hintpanel.style == "none") return;
        goog.net.XhrIo.send("/hinthistory/" + puzzle_id, goog.bind(function(e) {
            var code = e.target.getStatus();
            if (code == 200) {
                var response = /** @type{HintHistory} */ (e.target.getResponseJson());
                this.render_history(response);
            }
        }, this));
    }

    /** @param{HintHistory} response */
    render_history(response) {
        var ht = goog.dom.getElement("hinttext");
        if (response.history.length == 0) {
            this.history.innerHTML = "You have not requested any hints.";
            ht.setAttribute(
                "placeholder",
                "Describe what you've tried, where you're stuck\u2026");
            ht.setAttribute("rows", "9");
            return;
        }
        ht.setAttribute(
            "placeholder",
            "Ask a followup question\u2026");
        ht.setAttribute("rows", "3");
        this.history.innerHTML = "";
        var dl = goog.dom.createDom("DL");
        for (var i = 0; i < response.history.length; ++i) {
            var msg = response.history[i];
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

    // onkeydown(e) {
    //  if (e.keyCode == goog.events.KeyCodes.ENTER) {
    //      this.submit();
    //      e.preventDefault();
    //  } else if (e.keyCode == goog.events.KeyCodes.ESC) {
    //      this.close();
    //      e.preventDefault();
    //  }
    // }

    toggle() {
        if (!this.built) this.build();
        if (goog.dom.classlist.contains(this.hintpanel, "panel-visible")) {
            this.close();
        } else {
            this.show();
        }
    }

    show() {
        if (!this.built) this.build();
        goog.dom.classlist.addRemove(this.hintpanel, "panel-invisible",
                                     "panel-visible");
        this.update_history();
        // focus on input field, once slide-out animation is complete.
        //setTimeout(goog.bind(this.focus_input, this), 200);
        return false;
    }

    close() {
        goog.dom.classlist.addRemove(this.hintpanel, "panel-visible",
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

    add_toast(message, timeout, audio, color="blue") {
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
        this.list_el = goog.dom.getElement("list");

        /** @type{?Element} */
        this.highlight_el = null;
        /** @type{?Element} */
        this.mask_el = null;

        var mapdata = /** @type{MapData} */ (initial_json);
        this.shortname = mapdata.shortname;

        this.draw_map(mapdata);
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
            this.map_el.appendChild(el);
        }

        for (var i = 0; i < mapdata.items.length; ++i) {
            this.draw_item(mapdata.items[i]);
        }
    }

    draw_item(it) {
        if (it.icon_url) {
            var mask_el = null;
            if (it.mask_url) {
                mask_el = goog.dom.createDom("IMG", {
                    src: it.mask_url, className: "mask"});
                mask_el.style.left = "" + it.pos_x + "px";
                mask_el.style.top = "" + it.pos_y + "px";
                this.map_el.appendChild(mask_el);
            }

            var el = goog.dom.createDom("IMG", {
                src: it.icon_url, className: "icon"});
            el.style.left = "" + it.pos_x + "px";
            el.style.top = "" + it.pos_y + "px";
            this.map_el.appendChild(el);

            if (it.poly && it.name) {
                var area = goog.dom.createDom("AREA", {shape: "poly",
                                                       coords: it.poly,
                                                       href: it.url});
                this.mapmap_el.appendChild(area);

                goog.events.listen(area, goog.events.EventType.MOUSEENTER,
                                   goog.bind(this.item_enter, this, it, mask_el));
                goog.events.listen(area, goog.events.EventType.MOUSELEAVE,
                                   goog.bind(this.item_leave, this, it));
            }
        }

        if (it.name) {
            var a = [];
            if (it.new_open) {
                a.push(goog.dom.createDom("SPAN", {className: "newopen"}, "NEW"));
            }
            a.push(goog.dom.createDom("A", {href: it.url}, it.name));
            if (it.answer) {
                a.push(" \u2014 ");
                a.push(goog.dom.createDom("SPAN", {className: it.solved ? "solved" : "unsolved"},
                                          it.answer));
            }
            el = goog.dom.createDom("LI", null, a);
            this.list_el.appendChild(el);
        }
    }

    item_enter(it, mask_el) {
        this.item_leave(null);

        if (mask_el) {
            mask_el.style.display = "inline";
            this.mask_el = mask_el;
        }

        var ch = [it.name];
        if (it.answer) {
            ch.push(goog.dom.createDom("B", null,
                                       goog.dom.createTextNode(it.answer)));
        }

        var h = goog.dom.createDom("DIV", {className: "p"}, ch);
        h.style.left = "" + it.pos_x + "px";
        h.style.top = "" + it.pos_y + "px";
        h.style.width = "" + it.width + "px";
        h.style.height = "" + it.height + "px";

        this.map_el.appendChild(h);
        this.highlight_el = h;
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

class H2020_Counter {
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
                el.innerHTML = hunt2020.time_formatter.duration(now-since);
            } else {
                var until = el.getAttribute("data-until");
                if (until) {
                    var d = until - now;
                    if (d < 0) d = 0;
                    el.innerHTML = hunt2020.time_formatter.duration(d);
                }
            }
        }
    }
}

class H2020_FastPass {
    constructor() {
        this.build(/** @type{FastPassState} */ (initial_json));
    }

    /** @param{FastPassState} data */
    build(data) {
        var e_none = goog.dom.getElement("fphavenone");
        var e_some = goog.dom.getElement("fphavesome");
        if (data.expire_time.length == 0) {
            e_none.style.display = "initial";
            e_some.style.display = "none";
            return;
        }
        e_none.style.display = "none";
        e_some.style.display = "initial";

        var e_xlist = goog.dom.getElement("fpexpirelist");
        e_xlist.innerHTML = "";
        for (var i = 0; i < data.expire_time.length; ++i) {
            var s = goog.dom.createDom("SPAN", {className: "counter"});
            s.setAttribute("data-until", data.expire_time[i].toString());
            e_xlist.appendChild(goog.dom.createDom("LI", null, s));
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

        var e_ulist = goog.dom.getElement("fpusablelist");
        e_ulist.innerHTML = "";
        for (var i = 0; i < data.usable_lands.length; ++i) {
            var u = data.usable_lands[i];
            var a = goog.dom.createDom("A", null, u.title);
            goog.events.listen(a, goog.events.EventType.CLICK,
                               goog.bind(this.use, this, u.shortname));
            e_ulist.appendChild(goog.dom.createDom("LI", null, a));
        }
    }

    /** @param{string} shortname */
    use(shortname) {
        goog.net.XhrIo.send("/fastpass/" + shortname, function(e) {
            var code = e.target.getStatus();
            if (code != 204) {
                alert(e.target.getResponseText());
            }
        });
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
    fastpass: null,
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
    hunt2020.time_formatter = new H2020_TimeFormatter();
    hunt2020.toast_manager = new H2020_ToastManager();
    hunt2020.audio_manager = new H2020_AudioManager();
    hunt2020.counter = new H2020_Counter();

    hunt2020.waiter = new H2020_Waiter(new H2020_Dispatcher());
    hunt2020.waiter.start();

    // Only present on the puzzle pages.
    var a = goog.dom.getElement("submit");
    if (a) {
        hunt2020.submit_panel = new H2020_SubmitPanel();
        goog.events.listen(a, goog.events.EventType.CLICK,
                           goog.bind(hunt2020.submit_panel.toggle, hunt2020.submit_panel));

        a = goog.dom.getElement("hinttoggle");
        hunt2020.hint_panel = new H2020_HintPanel();
        goog.events.listen(a, goog.events.EventType.CLICK,
                           goog.bind(hunt2020.hint_panel.toggle, hunt2020.hint_panel));

        var e = goog.dom.getElement("emoji-picker-body");
        if (e) {
            goog.net.XhrIo.send(edb, goog.bind(emoji_builder, null, e));
        }
        if (puzzle_id && puzzle_init) puzzle_init();
    }

    // Only present on the map pages.
    var m = goog.dom.getElement("map");
    if (m) {
        hunt2020.map_draw = new H2020_MapDraw();
    }

    // Only present on the activity log page.
    var log = goog.dom.getElement("log");
    if (log) {
        for (var i = 0; i < log_entries.length; ++i) {
            var t = log_entries[i][0];
            var htmls = log_entries[i][1];

            var td = goog.dom.createDom("TD");

            var tr = goog.dom.createDom("TR",
                                        null,
                                        goog.dom.createDom("TH", null, hunt2020.time_formatter.format(t)),
                                        td);
            for (var j = 0; j < htmls.length; ++j) {
                if (j > 0) {
                    td.innerHTML += "<br>";
                }
                td.innerHTML += htmls[j];
            }
            log.appendChild(tr);
        }
    }

    // Only present on the fastpass page.
    if (goog.dom.getElement("fphavenone")) {
        hunt2020.fastpass = new H2020_FastPass();
    }
}
