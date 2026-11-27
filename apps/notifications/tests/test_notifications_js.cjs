// Run with: node --test apps/notifications/tests/test_notifications_js.cjs
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const source = fs.readFileSync(path.resolve(__dirname, "../../..", "static/js/components/notifications.js"), "utf8");
const now = 1800000000000;
const lifetime = 6 * 60 * 60 * 1000;
const key = (user = "user-a", company = "company-a", store = "store-a") =>
  `apudig:notification-count:v1:${user}:${company}:${store}`;
const entry = (count, updatedAt = now) => JSON.stringify({count, updatedAt});
const settle = () => new Promise(setImmediate);

class Element {
  constructor() {
    this.events = new Map();
    this.dataset = {};
    this.attributes = {};
    this.textContent = "";
    this.hidden = true;
    this.classList = {toggle() {}};
  }
  addEventListener(name, callback) {
    this.events.set(name, callback);
  }
  async fire(name, event = {}) {
    return this.events.get(name)?.(event);
  }
  setAttribute(name, value) {
    this.attributes[name] = value;
  }
  querySelector() { return null; }
  querySelectorAll() { return []; }
}

function mount({storage = new Map(), user = "user-a", company = "company-a", store = "store-a", blocked = false,
  respond = () => ({unread_count: 4, html: "fresh notifications"})} = {}) {
  const center = new Element();
  const badge = new Element();
  const body = new Element();
  const readAll = new Element();
  const trigger = new Element();
  const document = new Element();
  const window = new Element();
  const calls = [];
  const intervals = [];
  const navigation = [];
  const tabs = [new Element(), new Element()];
  tabs[0].dataset.notificationTab = "unread";
  tabs[1].dataset.notificationTab = "all";
  center.dataset = {userId: user, companyId: company, storeId: store,
    countUrl: "/count/", dropdownUrl: "/dropdown/", readAllUrl: "/read-all/"};
  const elements = new Map([
    ["[data-notification-badge]", badge], ["[data-notification-body]", body],
    ["[data-notification-read-all]", readAll], ["[data-bs-toggle='dropdown']", trigger],
  ]);
  center.querySelector = (selector) => elements.get(selector);
  center.querySelectorAll = () => tabs;
  document.querySelector = () => center;
  document.hidden = false;
  document.cookie = "csrftoken=test-csrf";
  window.location = {assign: (url) => navigation.push(url), reload() {}};
  window.setInterval = (...args) => intervals.push(args);
  window.localStorage = {
    getItem(name) {
      if (blocked) throw new Error("Storage blocked");
      return storage.get(name) ?? null;
    },
    setItem(name, value) {
      if (blocked) throw new Error("Storage blocked");
      storage.set(name, value);
    },
  };
  vm.runInNewContext(source, {
    document, window, Date: {now: () => now},
    fetch: async (url, options) => {
      calls.push({url, options});
      const data = await respond(url, options);
      return {ok: !data.errorStatus, status: data.errorStatus || 200, json: async () => data};
    },
  });
  return {badge, body, readAll, trigger, document, window, calls, intervals, storage, tabs, navigation};
}

test("first visit fetches once and subsequent pages reuse the scoped count without extending its age", async () => {
  const storage = new Map();
  const first = mount({storage});
  await settle();
  assert.equal(first.calls.length, 1);
  assert.equal(first.badge.textContent, "4");
  const saved = storage.get(key());
  const second = mount({storage});
  await settle();
  assert.equal(second.calls.length, 0);
  assert.equal(second.badge.textContent, "4");
  assert.equal(storage.get(key()), saved);
});

test("an expired count refreshes once on navigation", async () => {
  const h = mount({storage: new Map([[key(), entry(2, now - lifetime)]])});
  await settle();
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].url, "/count/");
  assert.equal(h.badge.textContent, "4");
  assert.equal(JSON.parse(h.storage.get(key())).updatedAt, now);
});

test("returning to a tab makes no request and no polling timer is installed", async () => {
  const h = mount({storage: new Map([[key(), entry(2)]])});
  for (let i = 0; i < 10; i++) {
    h.document.hidden = true;
    await h.document.fire("visibilitychange");
    h.document.hidden = false;
    await h.document.fire("visibilitychange");
  }
  await settle();
  assert.equal(h.intervals.length, 0);
  assert.equal(h.calls.length, 0);
});

test("opening the bell always fetches fresh list and count without an extra count request", async () => {
  const h = mount({storage: new Map([[key(), entry(2)]])});
  await h.trigger.fire("show.bs.dropdown");
  await h.trigger.fire("show.bs.dropdown");
  assert.deepEqual(h.calls.map((call) => call.url), ["/dropdown/?status=unread", "/dropdown/?status=unread"]);
  assert.equal(h.body.innerHTML, "fresh notifications");
  assert.equal(h.badge.textContent, "4");
  assert.equal(JSON.parse(h.storage.get(key())).count, 4);
  assert.equal(h.calls[0].options.cache, "no-store");
  assert.equal(h.calls[0].options.headers["X-Notification-Company"], "company-a");
  assert.equal(h.calls[0].options.headers["X-Notification-Store"], "store-a");
  assert.equal(h.calls[0].options.headers["X-Notification-User"], "user-a");
});

test("switching user, company or branch never reuses another scope's badge", async () => {
  for (const scope of [{user: "user-b"}, {company: "company-b"}, {store: "store-b"}]) {
    const storage = new Map([[key(), entry(99)]]);
    const h = mount({storage, ...scope});
    assert.equal(h.badge.hidden, true);
    await settle();
    assert.equal(h.calls.length, 1);
    assert.equal(h.badge.textContent, "4");
    assert.equal(JSON.parse(storage.get(key())).count, 99);
  }
});

test("marking all read updates the cached badge and refreshes the list", async () => {
  const h = mount({storage: new Map([[key(), entry(2)]]), respond: () => ({unread_count: 0, html: "no unread items"})});
  await h.readAll.fire("click");
  await settle();
  assert.equal(h.calls[0].url, "/read-all/");
  assert.equal(h.calls[0].options.method, "POST");
  assert.equal(h.calls[0].options.headers["X-CSRFToken"], "test-csrf");
  assert.equal(h.badge.hidden, true);
  assert.equal(JSON.parse(h.storage.get(key())).count, 0);
  assert.equal(h.body.innerHTML, "no unread items");
});

test("reading an individual notification saves the new count before navigating", async () => {
  const h = mount({storage: new Map([[key(), entry(2)]]), respond: (url) => ({
    unread_count: url === "/read/1/" ? 3 : 4, html: "fresh",
  })});
  const link = new Element();
  link.href = "/purchase/1/";
  link.dataset.readUrl = "/read/1/";
  h.body.querySelectorAll = () => [link];
  await h.trigger.fire("show.bs.dropdown");
  await link.fire("click", {preventDefault() {}});
  assert.equal(h.calls[1].url, "/read/1/");
  assert.equal(h.calls[1].options.method, "POST");
  assert.equal(JSON.parse(h.storage.get(key())).count, 3);
  assert.deepEqual(h.navigation, ["/purchase/1/"]);
});

test("storage events update matching tabs without a request or changing freshness", async () => {
  const storage = new Map([[key(), entry(2)]]);
  const h = mount({storage});
  await h.window.fire("storage", {key: key("user-a", "other-company"), newValue: entry(99)});
  assert.equal(h.badge.textContent, "2");
  await h.window.fire("storage", {key: key(), newValue: entry(0)});
  assert.equal(h.badge.hidden, true);
  assert.equal(storage.get(key()), entry(2));
  assert.equal(h.calls.length, 0);
});

test("blocked storage makes no automatic requests, while the bell still works", async () => {
  const h = mount({blocked: true});
  await settle();
  assert.equal(h.calls.length, 0);
  await h.trigger.fire("show.bs.dropdown");
  assert.equal(h.calls.length, 1);
  assert.equal(h.badge.textContent, "4");
});

test("failed refresh does not replace cached data and opening the bell retries", async () => {
  const saved = entry(2, now - lifetime);
  const h = mount({storage: new Map([[key(), saved]]), respond: (url) => {
    if (url === "/count/") throw new Error("Offline");
    return {unread_count: 3, html: "fresh"};
  }});
  await settle();
  assert.equal(h.storage.get(key()), saved);
  await h.trigger.fire("show.bs.dropdown");
  assert.equal(h.badge.textContent, "3");
});

test("a slow startup count cannot overwrite a newer dropdown result", async () => {
  let complete;
  const pending = new Promise((resolve) => { complete = resolve; });
  const h = mount({respond: (url) => url === "/count/" ? pending : {unread_count: 9, html: "fresh"}});
  await h.trigger.fire("show.bs.dropdown");
  complete({unread_count: 1});
  await settle();
  assert.equal(h.badge.textContent, "9");
  assert.equal(JSON.parse(h.storage.get(key())).count, 9);
});

test("invalid cached counts are ignored instead of leaking stale or malformed state", async () => {
  for (const invalid of ["bad-json", entry(-1), entry(2, now + 1000)]) {
    const h = mount({storage: new Map([[key(), invalid]])});
    await settle();
    assert.equal(h.calls.length, 1);
    assert.equal(h.badge.textContent, "4");
  }
});

test("an old tab rejected by the server keeps its own cache and prompts to reload", async () => {
  const saved = entry(2);
  const h = mount({storage: new Map([[key(), saved]]), respond: () => ({errorStatus: 404})});
  await h.trigger.fire("show.bs.dropdown");
  assert.equal(h.storage.get(key()), saved);
  assert.match(h.body.innerHTML, /data-notification-reload/);
});
