export default class PropertiesStore<Properties> {
    private map;
    properties(obj: object): Properties;
    get(key: object): Properties | undefined;
    set(key: object, value: Properties): WeakMap<object, Properties>;
    has(key: object): boolean;
    delete(key: object): boolean;
}
