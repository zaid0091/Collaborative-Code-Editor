export function createLocalAwareness() {
  const listeners = new Set();
  let state = {};

  return {
    getLocalState() {
      return state;
    },
    setLocalState(nextState) {
      state = nextState;
      listeners.forEach((listener) => listener(state));
    },
    on(event, listener) {
      if (event === "change") {
        listeners.add(listener);
      }
    },
    off(event, listener) {
      if (event === "change") {
        listeners.delete(listener);
      }
    },
  };
}
