/** @type{string} */
var puzzle_id;

/** @type{Array<Object>} */
var icons;

/** @type{Array<Object>} */
var log_entries;

class Message {
    constructor() {
	/** @type{string} */
	this.method;
	/** @type{string} */
	this.puzzle_id;
	/** @type{string} */
	this.title;
    }
}

class Submission {
    constructor() {
	/** @type{number} */
	this.submit_time;
	/** @type{number} */
	this.check_time;
	/** @type{string} */
	this.answer;
	/** @type{string} */
	this.state;
	/** @type{string} */
	this.response;
	/** @type{number} */
	this.submit_id;
    }
}

class SubmissionHistory {
    constructor() {
	/** @type{boolean} */
	this.allowed;
	/** @type{Array<Submission>} */
	this.history;
	/** @type{?number} */
	this.correct;
	/** @type{?number} */
	this.total;
    }
}



