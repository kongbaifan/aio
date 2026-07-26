import { MobileListItem, UIMetaFilterType, UIMetaMobileType } from '../../types/components';
import { I18ns } from '../../types/common';
import { Component } from '../common';
declare class List extends Component {
    titleAreaText: I18ns;
    objectApiName: string;
    listItems: MobileListItem;
    filter: UIMetaFilterType;
    sortConditions: object[];
    pageApiName: string;
    componentName: string;
    pageType: ('app' | 'record_page');
    needPublish: boolean;
    constructor(params: UIMetaMobileType);
    static parse(input: Record<string, any>): List;
    getReqParam(): Record<string, any>;
    getTableColumn(): {
        apiName: string;
    }[];
    getDescribeFilter(): {
        filter: string;
    };
}
export { List, };
