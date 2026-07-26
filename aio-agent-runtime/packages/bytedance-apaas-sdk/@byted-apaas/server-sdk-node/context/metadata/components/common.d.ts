declare const componentTypes: Record<string, string>;
declare class Component {
    private type;
    constructor(type: string);
}
export { Component, componentTypes, };
