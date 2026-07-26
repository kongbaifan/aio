import { Component } from '../common';
import { SelectFieldType } from '../../types/components';
import { I18ns } from '../../types/common';
declare class RecordDetail extends Component {
    titleAreaText: I18ns;
    objectApiName: string;
    selectedFields: SelectFieldType[];
    constructor(params: Record<string, any>);
    static parse(input: Record<string, any>): RecordDetail;
}
export { RecordDetail, };
