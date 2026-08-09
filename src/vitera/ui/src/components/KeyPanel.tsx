import { useState } from 'react'
import { DEFAULT_MODEL, keyStore } from '../llm'

/* Bring-your-own-key, for a judge who wants to see the prose layer run.
 *
 * Everything the product actually decides is already on the screen without
 * this. Detection is rules plus a self-hosted cross-encoder; the provider is
 * asked for one sentence of Indonesian explaining a finding that already
 * exists. So the honest framing on the panel is not "unlock the AI" but "turn
 * on the wording", and the copy says exactly that.
 *
 * Handling of the key:
 *   - sessionStorage only, so it dies with the tab. Never localStorage, never
 *     a cookie, never sent to us, never written to any file.
 *   - the call goes from the judge's browser straight to the provider, so the
 *     key does not transit a server of ours because there is not one.
 *   - the field is a password input and the panel says all of this in plain
 *     Bahasa, because a person typing a credential deserves to be told where
 *     it goes before they type it rather than after.
 */

export function KeyPanel({
  hasKey,
  onChange,
}: {
  hasKey: boolean
  onChange: () => void
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [model, setModel] = useState(keyStore.model())

  const save = () => {
    const v = draft.trim()
    if (!v) return
    keyStore.set(v)
    keyStore.setModel(model.trim())
    setDraft('')
    setOpen(false)
    onChange()
  }

  const clear = () => {
    keyStore.clear()
    onChange()
  }

  return (
    <div className="keypanel">
      <button
        className={'keytoggle' + (hasKey ? ' on' : '')}
        onClick={() => setOpen(!open)}
      >
        <span className="kled" />
        {hasKey ? 'Kunci API aktif' : 'Pakai kunci API sendiri'}
      </button>

      {open && (
        <div className="keybody">
          <p className="prose">
            Deteksi tidak memakai kunci ini. Temuan, skor, kutipan dan tarif
            sudah dihitung oleh aturan, cross-encoder dan grouper tanpa
            provider mana pun. Kunci hanya menyalakan satu hal: kalimat
            penjelasan pada tiap temuan.
          </p>

          <label>
            <span>Kunci OpenAI</span>
            <input
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder="sk-..."
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && save()}
            />
          </label>

          <label>
            <span>Model</span>
            <input
              type="text"
              spellCheck={false}
              placeholder={DEFAULT_MODEL}
              value={model}
              onChange={(e) => setModel(e.target.value)}
            />
          </label>

          <div className="keyacts">
            <button className="act primary" onClick={save} disabled={!draft.trim()}>
              Simpan untuk sesi ini
            </button>
            {hasKey && (
              <button className="act" onClick={clear}>
                Hapus kunci
              </button>
            )}
          </div>

          <ul className="keynote">
            <li>
              Disimpan di <b>sessionStorage</b> peramban Anda dan hilang saat
              tab ditutup. Tidak pernah ditulis ke disk, tidak pernah dikirim
              ke kami.
            </li>
            <li>
              Permintaan berangkat langsung dari peramban Anda ke provider.
              Kami tidak punya server di antaranya.
            </li>
            <li>
              Teks disamarkan lebih dulu (nama, NIK, nomor SEP, nomor rekam
              medis, tanggal, telepon) sebelum dikirim, sesuai aturan
              arsitektur 3. Data demo ini sintetis.
            </li>
            <li>
              Tanpa kunci, seluruh aplikasi tetap berjalan dengan penjelasan
              deterministik.
            </li>
          </ul>
        </div>
      )}
    </div>
  )
}
