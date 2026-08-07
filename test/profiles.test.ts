import { describe, expect, it } from "vitest"
import { bluetoothBaseUuid, detectDeskProfile } from "../src/index.js"

describe("desk profile detection", () => {
  it("selects the actual FF00 service even when the advertisement used 00FF", () => {
    const profile = detectDeskProfile([bluetoothBaseUuid(0x1800), bluetoothBaseUuid(0xff00)])
    expect(profile?.variant).toBe("jiecang_ff00")
    expect(profile?.inputCharacteristicUuid).toBe(bluetoothBaseUuid(0xff01))
  })
})
