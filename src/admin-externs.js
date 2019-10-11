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

/** @type{BBLabelInfo} */
var label_info;

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

class BBHintQueue {
    constructor() {
        /** @type{?number} */
        this.size;
        /** @type{?number} */
        this.claimed;
    }
}

class OpenPuzzle {
    constructor() {
        /** @type{string} */
        this.shortname;
        /** @type{string} */
        this.title;
        /** @type{number} */
        this.open_time;
        /** @type{?Array<string>} */
        this.answers_found;
    }
}

class SolvedPuzzle {
    constructor() {
        /** @type{string} */
        this.username;
        /** @type{string} */
        this.name;
        /** @type{number} */
        this.duration
    }
}

class LogEntry {
    constructor() {
        /** @type{number} */
        this.when;
        /** @type{Array<string>} */
        this.html;
    }
}

class TeamPageData {
    constructor() {
        /** @type{Array<OpenPuzzle>} */
        this.open_puzzles;
        /** @type{?Array<number>} */
        this.fastpasses;
        /** @type{Array<LogEntry>} */
        this.log;
    }
}

class PuzzlePageData {
    constructor() {
        /** @type{Array<SolvedPuzzle>} */
        this.solves;
        /** @type{Array<LogEntry>} */
        this.log;
        /** @type{number} */
        this.hint_time;
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

class TeamPuzzlePageData {
    constructor() {
        /** @type{Array<HintMessage>} */
        this.history;
        /** @type{?string} */
        this.claim;
        /** @type{string} */
        this.state;
        /** @type{?number} */
        this.open_time;
        /** @type{?number} */
        this.solve_time;
        /** @type{Array<LogEntry>} */
        this.log;
    }
}



class BBLandLabel {
    constructor() {
        /** @type{string} */
        this.symbol;
        /** @type{string} */
        this.color;
        /** @type{number} */
        this.left;
    }
}

class BBLabelInfo {
    constructor() {
        /** @type{Array<BBLandLabel>} */
        this.lands;
    }
}
