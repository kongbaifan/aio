import { Component } from '../common';
import { UIMetaFilterType, UIMetaDesktopType, DeskListDetailField, DeskListSubtitleField, DeskListTitleField } from '../../types/components';
import { I18ns } from '../../types/common';
declare class List extends Component {
    titleAreaText: I18ns;
    objectApiName: string;
    isCompositeType: boolean;
    titleFields: DeskListTitleField[];
    subtitleFields: DeskListSubtitleField[];
    detailFields: DeskListDetailField[];
    filter: UIMetaFilterType;
    sortConditions: object[];
    constructor(params: UIMetaDesktopType);
    static parse(input: Record<string, any>): List;
}
export { List, };
