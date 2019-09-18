/** @type{?string} */
var puzzle_id;

/** @type{MapData} */
var mapdata;

/** @type{Array<Object>} */
var log_entries;

/** @type{?function()} */
var puzzle_init;

/** @type{number} */
var waiter_id;

/** @type{number} */
var received_serial;

/** @type{Storage} */
var localStorage;

/** @type{Storage} */
var sessionStorage;

/** @type{?number} */
var open_time;

class Message {
    constructor() {
        /** @type{string} */
        this.method;
        /** @type{?string} */
        this.puzzle_id;
        /** @type{?string} */
        this.title;
        /** @type{?string} */
        this.audio;
        /** @type{?number} */
        this.new_start;
        /** @type{?string} */
        this.url;
        /** @type{?number} */
        this.score;
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
        /** @type{?string} */
        this.overlay;
        /** @type{?number} */
        this.width;
        /** @type{?number} */
        this.height;
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

class MapItem {
    constructor() {
        /** @type{string} */
        this.name;
        /** @type{string} */
        this.url;
        /** @type{boolean} */
        this.solved;
        /** @type{?string} */
        this.answer;
        /** @type{?string} */
        this.icon_url;
        /** @type{?string} */
        this.mask_url;
        /** @type{?number} */
        this.pos_x;
        /** @type{?number} */
        this.pos_y;
        /** @type{?number} */
        this.width;
        /** @type{?number} */
        this.height;
        /** @type{?string} */
        this.poly;
        /** @type{?string} */
        this.animate;
        /** @type{?boolean} */
        this.new_open;
    }
}

class MapData {
    constructor() {
        /** @type{?string} */
        this.base_url;
        /** @type{Array<MapItem>} */
        this.items;
    }
}
