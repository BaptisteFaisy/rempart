class LocalStorageMock {
  private store: Record<string, string> = {};

  clear() {
    this.store = {};
  }

  getItem(key: string) {
    return this.store[key] || null;
  }

  setItem(key: string, value: string) {
    this.store[key] = String(value);
  }

  removeItem(key: string) {
    delete this.store[key];
  }

  get length() {
    return Object.keys(this.store).length;
  }

  key(index: number) {
    const keys = Object.keys(this.store);
    return keys[index] || null;
  }
}

const mock = new LocalStorageMock();
Object.defineProperty(globalThis, 'localStorage', {
  value: mock,
  writable: true
});
if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'localStorage', {
    value: mock,
    writable: true
  });
}
