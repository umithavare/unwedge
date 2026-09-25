# unwedge

**Yapay zekâ kodlama ajanları için bir devre kesici.** unwedge, Claude Code, Codex CLI ya da
kendi ajan döngünüz bir yere takıldığında (aynı hatalı komut tekrar tekrar, görmezden gelinen
aynı hata, göreve hiç yaklaşmayan adımlar) bunu fark eder ve döngü bütçenizi yakmadan söyler.

İsim geliştirici argosundan geliyor: *wedged*, takılıp kalmış ve yardım almadan ilerleyemeyen bir
süreç demek. unwedge takılan ajanı fark eder, dürter; yetmezse size haber verir.

[English](README.md) · [Claude Code](docs/claude-code.md) · [Codex](docs/codex.md) ·
[Sağlayıcılar](docs/providers.md) · [Nasıl çalışır](docs/how-it-works.md) · [Benchmark](docs/benchmark.md)

> Ayrıntılı dokümanlar İngilizcedir. Bu sayfa kurulum ve kullanımın Türkçe özetidir.

---

Ajanlar tanıdık bir şekilde çuvallar: 9. adımda takılır, 60. adımda hâlâ aynı şeyi dener.
`max_turns`, token sınırları ve zaman aşımları bütçeyi korur ama davranışa bakmaz; para
harcandıktan sonra devreye girer. unwedge davranışa bakar:

```text
T6  edit 199:205 (+19 lines) -> edit REJECTED, not applied: F821 undefined name   S=0.97 P0=0.13
T7  edit 199:205 (+19 lines) -> edit REJECTED, not applied: F821 undefined name   S=0.97 P0=0.18
T8  edit 199:205 (+19 lines) -> edit REJECTED, not applied: F821 undefined name   S=0.97 P0=0.19  <<< ipucu
    [UNWEDGE] You have run this command 4 times with the same result. Change something before
    running it again, or step back and re-read the error.
T11 ...                                                                                            <<< ipucu
T14 ...                                                                                            <<< eskalasyon
```

*Benchmark'tan gerçek bir SWE-agent oturumu, canlı jev kararlarıyla yeniden oynatıldı
(S = takılma, P0 = hiç ilerleme olmama olasılığı). Ajanın düzenlemesi üst üste 31 kez
reddedildi; oturum harcamasının %94'ü unwedge'in ilk ipucundan sonra yapıldı.*

## Ne yapar

- **Her araç çağrısını bir hook ile kaydeder** ve döngü sinyallerini kodla hesaplar: arada hiçbir
  şey değişmeden tekrarlanan komutlar, tekrar eden sonuçlar, aynı hata imzası, seriler.
  Ücretsiz ve yereldir.
- **İsterseniz tipli karar veren bir modele** kodun cevaplayamadığı soruları sorar: ajan hâlâ
  göreve yaklaşıyor mu, iş zaten bitmiş mi, konu dışına mı kaydı? Sağlayıcılar:
  [TypeSafe jev](https://docs.typesafe.ai) (bulutta) veya
  [Laya](https://github.com/NandhaKishorM/laya) (açık ağırlıklı, kendi makinenizde; Apple
  silicon'da [laya-mlx](https://github.com/mizorewww/laya-mlx)). Model yalnızca olasılık
  döndürür, ajanınıza asla metin yazmaz.
- **Moduna göre davranır:** `shadow` yalnızca kaydeder; `hint` ajanın bağlamına insan tarafından
  yazılmış kısa bir ipucu ekler; `stop` (isteğe bağlı) iki ipucundan sonra da dönmeye devam eden
  bir oturumu bitirebilir.
- **Ajanı asla bozmaz:** sağlayıcıda ya da hook'ta her sorun "fail open" olur, yani ajan
  kaldığı yerden devam eder.

## Hızlı başlangıç

```bash
uv tool install unwedge   # ya da: pipx install unwedge / pip install unwedge
unwedge scan        # son Claude Code ve Codex oturumlarınızı tarar, döngüleri işaretler; ücretsiz, yerel
unwedge doctor      # ayarları ve sağlayıcıyı kontrol eder
```

**Claude Code**

```text
/plugin marketplace add umithavare/unwedge
/plugin install unwedge@unwedge
```

Eklenti arka planda çalışır (gecikme eklemez) ve etkinleştirirken mod ile sağlayıcıyı sorar.
Elle `settings.json` kurulumu ve stop modu: [docs/claude-code.md](docs/claude-code.md).

**Codex CLI** (0.124+): `~/.codex/hooks.json` dosyasına ekleyin, sonra `/hooks` içinde onaylayın:

```json
{ "hooks": { "PostToolUse": [{ "hooks": [{ "type": "command", "command": "unwedge hook", "timeout": 15 }] }] } }
```

Eklenti pazaryeri dahil ayrıntılar: [docs/codex.md](docs/codex.md).

**Kendi ajan döngünüz**

```python
from unwedge import Guard, GuardConfig, make_provider
from unwedge.adapters.generic import turn_from_command

provider = make_provider("none")                      # veya "jev", "laya"
guard = Guard(goal=task, provider=provider, config=GuardConfig.for_provider(provider, shadow=False))
outcome = guard.on_turn(turn_from_command(index, command, output))
if outcome.hint_text:
    next_message += outcome.hint_text
```

Ayrıntılar: [docs/python-api.md](docs/python-api.md).

## Sağlayıcı seçimi

| | `none` (varsayılan) | `jev` | `laya` |
|---|---|---|---|
| nerede çalışır | yerelde, yalnızca kod | TypeSafe API (ABD) | kendi makinenizde (`laya-serve` veya `unwedge serve`) |
| değerlendirilen adım başına maliyet | ücretsiz | ~0,0001 $ | ücretsiz |
| değerlendirilen adım başına gecikme | yok | p50 0,32 sn, p99 0,64 sn | CPU'da (8 iş parçacığı) p50 2,4 sn (`multilingual`) ile 4,1 sn (`english`) arası; GPU ve Apple silicon ölçülmedi |
| benchmark'ta yalnızca koda göre kazanç | – | kontrolden çıkan oturum yakalamada +5 puan, kurtarılan harcamada +8 puan | deneysel: henüz kazanç ölçülmedi |
| veri makineden çıkar mı | hayır | evet (gizli bilgileri temizlenmiş bir özet) | hayır |

`UNWEDGE_PROVIDER` ortam değişkeniyle veya eklenti ayarından seçilir:

```bash
export UNWEDGE_PROVIDER=jev   TYPESAFE_API_KEY=...          # bulut
export UNWEDGE_PROVIDER=laya  LAYA_MODEL=english            # yerel: önce `unwedge serve` veya `laya-serve`
```

Her birinin kurulumu: [docs/providers.md](docs/providers.md).

## Sonuçlar

Herkese açık bir veri setinden 218 gerçek ajan oturumunu (SWE-bench görevlerinde SWE-agent) adım
adım unwedge'den geçirdik; tüm eşikler veriye bakmadan önce sabitlendi. "Kontrolden çıkan"
oturumlar, bağlam bütçesini tüketerek biten oturumlar.

| kurulum | yakalanan kontrolden çıkan oturum | ilk uyarıdan sonraki harcama payı | ipucu alan başarılı oturum |
|---|---|---|---|
| yalnızca kod (`provider=none`, ücretsiz) | %60 | %47 | 69'da 5 |
| **kod + jev (önerilen)** | **%65** | **%55** | **69'da 5** |

- **Kontrolden çıkan oturumların çoğunu erkenden yakalıyor:** %65'i, genellikle oturumun
  yarısında işaretlendi.
- **Gerçek para kurtarıyor:** bu oturumların harcamasının %55'i unwedge'in ilk uyarısından sonra
  yapılmıştı; orada durdurmak bu kadarını kurtarırdı.
- **Sağlıklı oturumları nadiren rahatsız ediyor:** 69 başarılı oturumun 5'i bir ipucu aldı.
  İpucu kısa bir mesajdır, oturumu durdurmaz; yanlış giden bir ipucunun maliyeti küçüktür.
- **Ücretsiz de işe yarıyor:** kod katmanı model ya da API anahtarı istemez. jev, oturum başına
  yaklaşık 0,003 $ ile yakalamaya 5 puan ekler.
- **Önce ipucu, durdurma isteğe bağlı:** unwedge ajanı dürter, döngü sürerse size haber verir;
  oturumu yalnızca isteğe bağlı stop modunda durdurur.

Yöntem, çapraz doğrulama, gecikme, maliyet ve sınırlamalar: [docs/benchmark.md](docs/benchmark.md).
Hepsi [`benchmarks/`](benchmarks) klasöründen yeniden üretilebilir.

## Modlar

| | shadow | hint | stop |
|---|---|---|---|
| her araç çağrısını ve kararı kaydeder | ✓ | ✓ | ✓ |
| ajanın bağlamına ipucu ekler | | ✓ | ✓ |
| ipuçları işe yaramazsa ajana durup kullanıcıya sormasını söyler | | ✓ | ✓ |
| oturumu bitirir (Claude Code, yalnızca senkron hook ile) | | | ✓ |

`unwedge report` hook'ların gördüklerini özetler; `unwedge replay <dosya>` bir oturumu adım
adım gösterir.

## Gizlilik ve güvenlik

Araç çıktıları, saklanmadan (`~/.unwedge`, 7 gün sonra silinir) ya da bir sağlayıcıya
gönderilmeden önce yaygın gizli bilgilerden (API anahtarları, token'lar, özel anahtarlar vb.)
temizlenir ve kırpılır. `none` veya `laya` ile hiçbir veri makinenizden çıkmaz. unwedge bir
maliyet ve canlılık korumasıdır, **güvenlik kontrolü değildir**. Bkz. [SECURITY.md](SECURITY.md).

## Durum

Alfa (0.1). Linux, macOS ve Windows'ta, Python 3.10-3.13 ile test edildi. Claude Code ve Codex CLI
desteği bu araçların belgelenmiş hook API'lerini izler; `scan` ve `replay` yerel oturum kayıtlarını
elden geldiğince okur. Gerçek oturumlardan geri bildirim çok değerli: lütfen bir issue açın.

## Katkı ve lisans

Issue ve pull request'ler memnuniyetle karşılanır: [CONTRIBUTING.md](CONTRIBUTING.md).
Lisans Apache-2.0. TypeSafe ve jev, TypeSafe AI'nin ürünleridir; Laya Convai Innovations'a
aittir; laya-mlx bağımsız bir MLX portudur. Bu proje bağımsızdır ve hiçbiriyle bağlantılı
değildir.
