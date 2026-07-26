import { I18ns } from './common';
export type SelectFieldType = {
    fieldPath: {
        objectApiName: string;
        fieldApiName: string;
    }[];
};
export type FieldApiType = {
    type?: string;
    fieldApiName: string;
    alias?: I18ns;
    concatText?: {
        zh_CN?: Object[];
        en_US?: Object[];
    };
    color?: string;
};
export type UIMetaFilterType = {
    conditions: Object[];
    logic: string;
};
export type UIMetaSortConditionsType = {
    fieldApiName: string;
    sort: string;
};
export type DeskListTitleField = {
    fieldApiName: string;
};
export type DeskListSubtitleField = {
    type?: ('field' | 'concatText');
    fieldApiName: string;
    alias: I18ns;
    concatText?: {
        zh_CN: ConcatTextType[];
        en_US: ConcatTextType[];
    };
};
export type DeskListDetailField = {
    fieldApiName: string;
    alias: I18ns;
};
export type UIMetaDesktopType = {
    isCompositeType: boolean;
    titleAreaText: I18ns;
    objectApiName: string;
    titleFields: FieldApiType[];
    subtitleFields: FieldApiType[];
    detailFields: FieldApiType[];
    filter: UIMetaFilterType;
    sortConditions: UIMetaSortConditionsType[];
};
export type UIMetaLangType = {
    dataType: string;
    fieldApiName: string;
    text: string;
};
export type ConcatTextType = {
    dataType: 'fieldApiName' | 'text';
    fieldApiName: string;
    text: string;
};
export type UIMetaMobileType = {
    pageType?: ('app' | 'record_page');
    pageApiName: string;
    componentName: string;
    titleAreaText: I18ns;
    objectApiName: string;
    listItems: MobileListItem;
    filter: UIMetaFilterType;
    sortConditions: UIMetaSortConditionsType[];
};
export type MobileListField = {
    fieldApiName: string;
    hiddenWhenEmpty?: boolean;
};
export type MobileListItem = {
    avatar: {
        active: boolean;
        fieldApiName: string;
    };
    titleFields: {
        fieldApiName: string;
    }[];
    tagFields: {
        fieldApiName: string;
        color: 'grey' | 'blue' | 'cyan' | 'green' | 'yellow' | 'orange' | 'red' | 'magenta' | 'purple' | 'blueMagenta';
    }[];
    subtitleFields: MobileListField[];
    detailFields: MobileListField[];
};
