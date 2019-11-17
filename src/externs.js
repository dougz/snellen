/** @type{?string} */
var puzzle_id;

/** @type{?function()} */
var puzzle_init;

/** @type{Storage} */
var localStorage;

/** @type{?number} */
var open_time;

// emoji database URL
/** @type{?string} */
var edb;
// emoji images base URL
/** @type{?string} */
var eurl;

/** @type{?Object} */
var initial_json;

/** @type{?Message} */
var initial_header;

/** @type{number} */
var received_serial;

/** @type{Storage} */
var sessionStorage;

class Message {
    constructor() {
        /** @type{string} */
        this.method;
        /** @type{?string} */
        this.puzzle_id;
        /** @type{?string} */
        this.title;
        /** @type{?string} */
        this.land;
        /** @type{?string} */
        this.audio;
        /** @type{?number} */
        this.new_start;
        /** @type{?string} */
        this.url;
        /** @type{?number} */
        this.score;
        /** @type{?boolean} */
        this.notify;
        /** @type{?FastPassState} */
        this.fastpass;
        /** @type{?MapData} */
        this.mapdata;
        /** @type{?Array<string>} */
        this.maps;
        /** @type{?Array<Array<string>>} */
        this.lands;
        /** @type{?string} */
        this.to_go;
        /** @type{?string} */
        this.video_url;
        /** @type{?string} */
        this.thumb;
        /** @type{?number} */
        this.passes;
        /** @type{?string} */
        this.stuff;
        /** @type{?Array<boolean>} */
        this.completed;
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
        /** @type{Array<number>} */
        this.xywh;
        /** @type{?string} */
        this.poly;
        /** @type{?string} */
        this.animate;
        /** @type{?number} */
        this.new_open;
        /** @type{?MapItem} */
        this.special;
        /** @type{?boolean} */
        this.spaceafter;
    }
}

class MapData {
    constructor() {
        /** @type{?string} */
        this.base_url;
        /** @type{number} */
        this.width;
        /** @type{number} */
        this.height;
        /** @type{string} */
        this.shortname;
        /** @type{Array<MapItem>} */
        this.items;
    }
}

class Land {
    constructor() {
        /** @type{string} */
        this.shortname;
        /** @type{string} */
        this.title;
        /** @type{?string} */
        this.url;
    }
}

class FastPassState {
    constructor() {
        /** @type{Array<number>} */
        this.expire_time;
        /** @type{Array<Land>} */
        this.usable_lands;
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

class ActivityLogData {
    constructor() {
        /** @type{Array<LogEntry>} */
        this.log;
    }
}

class Achievement {
    constructor() {
        /** @type{string} */
        this.name;
        /** @type{string} */
        this.subtitle;
    }
}

class AllPuzzles {
    constructor() {
        /** @type{Array<APLand>} */
        this.lands;
    }
}

class APLand {
    constructor() {
        /** @type{string} */
        this.title;
        /** @type{string} */
        this.url;
        /** @type{Array<APPuzzle>} */
        this.puzzles;
    }
}

class APPuzzle {
    constructor() {
        /** @type{string} */
        this.title;
        /** @type{string} */
        this.url;
        /** @type{?string} */
        this.answer;
        /** @type{?boolean} */
        this.spaceafter;
    }
}




