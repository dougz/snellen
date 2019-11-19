/** @type{?string} */
var puzzle_id;
/** @type{?string} */
var team_username;

/** @type{?Array<Array<string>>} */
var puzzle_list;
/** @type{?Array<Array<string>>} */
var team_list;

/** @type{BBLabelInfo} */
var label_info;

/** @type{number} */
var received_serial;

/** @type{Storage} */
var sessionStorage;

// emoji database URL
/** @type{?string} */
var edb;
// emoji images base URL
/** @type{?string} */
var eurl;

/** @type{string} */
var page_class;

class Message {
    constructor() {
        /** @type{string} */
        this.method;
        /** @type{?string} */
        this.team_username;
        /** @type{?string} */
        this.puzzle_id;
        /** @type{?string} */
        this.favicon;
    }
}

class TaskQueue {
    constructor() {
        /** @type{Array<TaskQueueItem>} */
        this.queue;
    }
}

class TaskQueueItem {
    constructor() {
        /** @type{string} */
        this.team;
        /** @type{string} */
        this.key;
        /** @type{string} */
        this.what;
        /** @type{number} */
        this.when;
        /** @type{string} */
        this.target;
        /** @type{string} */
        this.claim;
        /** @type{?string} */
        this.claimant;
        /** @type{?boolean} */
        this.done_pending;
    }
}

class BBTaskQueue {
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
        /** @type{string} */
        this.symbol;
        /** @type{string} */
        this.color;
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
        this.htmls;
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
        /** @type{string} */
        this.svg;
        /** @type{number} */
        this.score;
    }
}

class PuzzlePageData {
    constructor() {
        /** @type{number} */
        this.median_solve;
        /** @type{number} */
        this.open_count;
        /** @type{number} */
        this.submitted_count;
        /** @type{number} */
        this.solve_count;
        /** @type{Array<number, string>} */
        this.incorrect_answers;
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
        /** @type{?boolean} */
        this.admin_only;
    }
}

class Submission {
    constructor() {
        /** @type{?number} */
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
        /** @type{Array<Submission>} */
        this.submits;
        /** @type{boolean} */
        this.hints_open;
    }
}

class ServerPageData {
    constructor() {
        /** @type{number} */
        this.waits;
        /** @type{number} */
        this.sessions;
        /** @type{Array<number>} */
        this.proxy_waits;
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

class BBTeamData {
    constructor() {
        /** @type{number} */
        this.score;
        /** @type{number} */
        this.score_change;
        /** @type{string} */
        this.name;
        /** @type{string} */
        this.username;
        /** @type{string} */
        this.svg;
        /** @type{?Element} */
        this.el;
    }
}

class FixResult {
    constructor() {
        /** @type{boolean} */
        this.success;
        /** @type{string} */
        this.message;
    }
}

