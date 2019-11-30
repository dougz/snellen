/** @type{Object<string, Team>} */
var team_data;

class Team {
    constructor() {
        /** @type{string} */
        this.name;
        /** @type{string} */
        this.location;
        /** @type{string} */
        this.phone;
        /** @type{string} */
        this.key;
    }
}

class Complete {
    constructor() {
        /** @type{string} */
        this.action;
        /** @type{string} */
        this.which;
        /** @type{string} */
        this.key;
        /** @type{boolean} */
        this.immediate;
    }
}

