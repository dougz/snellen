/** @type{?string} */
var puzzle_id;
/** @type{?string} */
var team_username;

/** @type{number} */
var waiter_id;

/** @type{number} */
var received_serial;

class Message {
    constructor() {
	/** @type{string} */
	this.method;
	/** @type{?string} */
	this.team_username;
	/** @type{?string} */
	this.puzzle_id;
    }
}

class HintMessage {
    constructor() {
	/** @type{string} */
	this.sender;
	/** @type{number} */
	this.when;
	/** @type{string} */
	this.text;
    }
}

class HintHistory {
    constructor() {
	/** @type{Array<HintMessage>} */
	this.history;
    }
}

