import { Component } from './common';
import { RecordDetail as DesktopRecordDetail } from './desktop/recordDetail';
import { List as DesktopList } from './desktop/list';
import { List as MobileList } from './mobile/list';
declare const desktop: {
    RecordDetail: typeof DesktopRecordDetail;
    List: typeof DesktopList;
};
declare const mobile: {
    List: typeof MobileList;
};
export { Component, desktop, mobile, };
