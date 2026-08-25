import { platformName } from "../../types";
import { useStore } from "../../lib/store";

export function DecisionReport() {
  const { report, verifyAfterClick, candidates } = useStore();

  if (!report || !report.picks.length) {
    return <div className="empty">完成需求确认后,这里会生成推荐结论与风险提示</div>;
  }

  return (
    <div className="report">
      <p className="summary">{report.summary}</p>

      {report.picks.map((pick) => {
        const candidate = candidates.find((item) => item.group_id === pick.group_id);
        const offer = candidate?.offers.find((item) => item.platform === pick.platform);
        return (
          <div key={pick.group_id} className="pick">
            <div className="pick-head">
              <span className="tag">{pick.label}</span>
              <strong>{pick.title}</strong>
              <span className="pick-price">
                ¥{pick.final_price.toLocaleString()}
                <em>{platformName(pick.platform)}</em>
              </span>
            </div>

            {pick.summary && <div className="pick-spec">{pick.summary}</div>}

            {pick.needs_recheck && (
              <div className="recheck">该价格未能实时确认,请到商品页核对</div>
            )}

            <div className="reasons">
              {pick.pros.map((item) => <div key={item} className="pro">+ {item}</div>)}
              {pick.cons.map((item) => <div key={item} className="con">− {item}</div>)}
            </div>

            {pick.price_spread && pick.price_spread.saved > 0 && (
              <div className="spread">
                跨平台最大价差 ¥{pick.price_spread.saved.toLocaleString()}
              </div>
            )}

            {offer && offer.url && (
              <a
                className="btn primary"
                href={offer.url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => void verifyAfterClick(offer.offer_id)}
              >
                前往 {platformName(pick.platform)} 购买
              </a>
            )}
          </div>
        );
      })}

      <p className="disclaimer">
        本站只提供选购建议与跳转,不代下单、不收集支付信息。价格以平台页面实际结算为准。
      </p>
    </div>
  );
}