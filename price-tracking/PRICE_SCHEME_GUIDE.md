# Price Tracking - Alert 기준 가이드라인

## 원칙
Price Change Alert 비교 기준은 **조건부 할인 전 가격(sl)**을 사용한다.
조건부 할인(캐시백, 프로모 코드, 카드 할인)은 별도 정보성 컬럼으로 표시한다.

## 필드 정의
| 필드 | 의미 | Alert 기준 사용 |
|------|------|----------------|
| `sp` | 표준가 (Standard Price) | ❌ |
| `sl` | 프로모가 (Sale/Promo Price) | ✅ 기본 기준 |
| `fp` | 최종가 (조건부 할인 적용 후) | ❌ 정보성 컬럼 |
| `fj` | 특수 카드가 (Al Ahli 등) | ✅ 별도 탭 기준 |

## 조건부 할인 판별 기준
아래 필드가 스크래퍼 스키마에 존재하면 → `sl` 기준, `fp` 정보성 컬럼 적용

- `cashback` / `cashback_amount` → 캐시백
- `promo_code` / `Offer_Detail` → 프로모 코드
- `only_pay` / `bank_price` → 카드/뱅크 할인

## 채널별 현재 상태 (2026-04-26 기준)
| 채널 | 조건부 할인 | Alert 기준 | 상태 |
|------|-----------|-----------|------|
| eXtra | Promo Code (extra10 → ×0.9) | sl | ✅ |
| SWS | Cashback (SAR) | sl | ✅ |
| Al Khunizan | Only Pay Price | sl | ✅ |
| Al Manea | Cashback (×0.9) | sl | ✅ |
| Black Box | BP멤버십(별도탭) | fp(cascade) | ✅ |
| BH | 없음 | cp | ✅ |
| Bin Momen | 없음 | sl | ✅ |
| Tamkeen | 없음 | sl | ✅ |
| Najm | 없음 | sl | ✅ |
| Technobest | 없음 | sl | ✅ |

## 사용자 개입 필요 시점
1. 새 채널 추가 시 → 조건부 할인 필드 확인 후 보고
2. 기존 채널 스크래퍼 스키마 변경 시 → 영향 파악 후 보고
3. 조건부 할인의 "항상성" 판단 필요 시 → 보고 (예: 상시 캐시백인지 한시적인지)
