/** @type{?string} */
var puzzle_id;
/** @type{?string} */
var team_username;

/** @type{number} */
var waiter_id;

/** @type{number} */
var received_serial;

/** @type{?Array<Array<string>>} */
var puzzle_list;
/** @type{?Array<Array<string>>} */
var team_list;

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
        /** @type{?string} */
        this.claim;
    }
}

class HintQueue {
    constructor() {
        /** @type{Array<HintQueueItem>} */
        this.queue;
    }
}

class HintQueueItem {
    constructor() {
        /** @type{string} */
        this.team;
        /** @type{string} */
        this.puzzle;
        /** @type{number} */
        this.when;
        /** @type{string} */
        this.target;
        /** @type{string} */
        this.claim;
        /** @type{?string} */
        this.claimant;
    }
}

