import { I18ns } from '../types/common';
declare class Objects {
    label: I18ns;
    apiName: string;
    displayName: string;
    searchSupplementaryInfo: any[];
    searchableFields: any[];
    fields: any[];
    constructor(obj: Record<string, any>);
}
export { Objects as Object, };
