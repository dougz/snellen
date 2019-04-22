/** @type{string} */
var puzzle_id;

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
    }
}




