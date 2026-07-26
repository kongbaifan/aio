import { Browser, Page } from 'puppeteer-core';
export declare const getCurrentPage: (browser: Browser) => Promise<{
    activePage: Page;
    activePageId: number;
}>;
export declare const getTabList: (browser: Browser, activePageId: number) => Promise<{
    index: number;
    active: boolean;
    title: string;
    url: string;
}[]>;
export declare function ensureBrowser(): Promise<{
    browser: Browser;
    page: Page;
    currTabsIdx: number;
}>;
