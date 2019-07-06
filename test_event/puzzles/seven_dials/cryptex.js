goog.require("goog.dom");
goog.require("goog.events");

class Cryptex {
    constructor() {
	this.setting = [0,0,0,0,0,0,0];
	// this.text = ["CSBPEDSIPT",
	// 	     "ERXRENUROT",
	// 	     "OAECDRAURA",
	// 	     "INERDMSTEP",
	// 	     "IUISIXONTE",
	// 	     "ERTNCNEOES",
	// 	     "NDERYSGTER"];
	this.text = ["LSCABKMBGN",
		     "IIARRREIAI",
		     "TLLSOYRSLO",
		     "HICEMPCMLB",
		     "ICINITUUII",
		     "UOUINORTUU",
		     "MNMCENYHMM"];

	for (var c = 0; c < 7; ++c) {
	    this.setting[c] = Math.floor(Math.random() * 10);

	    var el = goog.dom.getElement("up_" + c);
	    goog.events.listen(el, goog.events.EventType.CLICK, goog.bind(this.shift, this, c, 1));
	    el = goog.dom.getElement("down_" + c);
	    goog.events.listen(el, goog.events.EventType.CLICK, goog.bind(this.shift, this, c, -1));
	}

	this.update();
    }

    update() {
	for (var c = 0; c < 7; ++c) {
	    for (var r = 0; r < 10; ++r) {
		document.getElementById("c_" + r + "_" + c).innerHTML =
		    this.text[c].charAt((r + this.setting[c]) % 10);
	    }
	}
    }

    shift(c, d) {
	this.setting[c] += d;
	if (this.setting[c] < 0) { this.setting[c] += 10; }
	if (this.setting[c] >= 10) { this.setting[c] -= 10; }
	this.update();
    }
}

var cryptex = null;

puzzle_init = function() {
    cryptex = new Cryptex();
}
