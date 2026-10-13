import assert from "node:assert/strict";
import test from "node:test";
import { isPrivateIp } from "./url-safety.js";

test("blocks private IPv4 ranges", () => {
  assert.equal(isPrivateIp("127.0.0.1"), true);
  assert.equal(isPrivateIp("10.2.3.4"), true);
  assert.equal(isPrivateIp("192.168.1.1"), true);
});

test("allows public IP addresses", () => {
  assert.equal(isPrivateIp("8.8.8.8"), false);
  assert.equal(isPrivateIp("1.1.1.1"), false);
});
