/**
 * BillingPage — Complete billing and subscription management.
 * Features: Plan comparison, usage tracking, payment methods, invoices.
 */
import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft, Zap, Users, Shield, CheckCircle2, CreditCard,
  AlertCircle, Loader2, BarChart2, Database, Bot, Receipt,
  ChevronDown, ChevronUp, Download, Star, Sparkles, TrendingUp,
  ArrowRight, Minus, Plus, Calendar, Clock, Info,
} from "lucide-react";
import { fetchBillingMe, fetchPlans, createCheckout } from "../services/api";

const TIER_COLORS = {
  free: "#6b7280",
  starter: "#8b5cf6",
  pro: "#6366f1",
  team: "#0891b2",
  enterprise: "#059669"
};

const TIER_GRADIENTS = {
  free: "linear-gradient(135deg, #374151 0%, #4b5563 100%)",
  starter: "linear-gradient(135deg, #7c3aed 0%, #8b5cf6 100%)",
  pro: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
  team: "linear-gradient(135deg, #0891b2 0%, #06b6d4 100%)",
  enterprise: "linear-gradient(135deg, #059669 0%, #10b981 100%)"
};

const TIER_ICONS = {
  free: Shield,
  starter: Star,
  pro: Zap,
  team: Users,
  enterprise: TrendingUp
};

function UsageBar({ label, used, limit, icon: Icon, color }) {
  const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const barColor = pct >= 90 ? "var(--red)" : pct >= 70 ? "var(--amber)" : color || "var(--accent)";
  
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-1)", fontWeight: 500 }}>
          {Icon && <Icon size={13} style={{ color }} />}
          {label}
        </span>
        <span style={{ fontSize: 11, color: "var(--text-2)", fontFamily: "'JetBrains Mono', monospace" }}>
          {used?.toLocaleString()}{limit ? ` / ${limit.toLocaleString()}` : " / ∞"}
        </span>
      </div>
      <div style={{ height: 6, background: "var(--surface-3)", borderRadius: 99, overflow: "hidden" }}>
        <div style={{
          width: `${pct}%`, height: "100%",
          background: pct >= 90 ? "var(--red)" : pct >= 70 ? "var(--amber)" : color || "var(--accent)",
          borderRadius: 99, transition: "width .5s ease"
        }} />
      </div>
    </div>
  );
}

function PlanCard({ plan, isCurrent, onUpgrade, upgrading, accentColor }) {
  const [expanded, setExpanded] = useState(false);
  const PlanIcon = TIER_ICONS[plan.id] || Shield;
  const color = TIER_COLORS[plan.id] || "#6b7280";

  return (
    <div className={`bp-plan-card ${isCurrent ? "bp-plan-card--current" : ""}`}
      style={{
        border: isCurrent ? `2px solid ${color}` : "1px solid var(--border)",
        background: isCurrent ? `linear-gradient(135deg, ${color}08 0%, var(--surface-1) 100%)` : "var(--surface-1)"
      }}>
      {plan.popular && (
        <div className="bp-popular-badge">
          <Sparkles size={10} /> Most Popular
        </div>
      )}

      <div className="bp-plan-header">
        <div className="bp-plan-icon" style={{ background: `${color}15`, border: `1px solid ${color}30` }}>
          <PlanIcon size={20} color={color} />
        </div>
        <div>
          <h3 className="bp-plan-name">{plan.name}</h3>
          <div className="bp-plan-price">
            {plan.price_monthly === 0 ? (
              <span style={{ color: "var(--text-1)" }}>Free</span>
            ) : (
              <>
                <span style={{ fontSize: 28, fontWeight: 800, color: "var(--text-0)" }}>${plan.price_monthly}</span>
                <span style={{ color: "var(--text-3)", fontSize: 12 }}>/month</span>
              </>
            )}
          </div>
          {plan.price_annual && (
            <div style={{ fontSize: 11, color: "var(--green)", marginTop: 2 }}>
              Save ${(plan.price_monthly * 12 - plan.price_annual).toFixed(0)}/year with annual
            </div>
          )}
        </div>
      </div>

      {isCurrent ? (
        <div className="bp-current-badge">
          <CheckCircle2 size={14} /> Your Current Plan
        </div>
      ) : plan.id !== "free" ? (
        <button
          className="bp-upgrade-btn"
          style={{
            background: plan.popular ? `var(--gradient-primary)` : "var(--surface-2)",
            border: plan.popular ? "none" : "1px solid var(--border)",
            color: plan.popular ? "#fff" : "var(--text-0)"
          }}
          onClick={() => onUpgrade(plan.id)}
          disabled={!!upgrading}
        >
          {upgrading === plan.id ? (
            <Loader2 size={14} style={{ animation: "spin .7s linear infinite" }} />
          ) : plan.price_monthly > 0 ? (
            <>
              <Zap size={14} /> Upgrade to {plan.name}
            </>
          ) : (
            <>
              <ArrowRight size={14} /> Downgrade to Free
            </>
          )}
        </button>
      ) : (
        <div className="bp-free-info">
          <span>Free forever</span>
        </div>
      )}

      <button
        className="bp-features-toggle"
        onClick={() => setExpanded(!expanded)}
      >
        <span>{plan.features?.length || 0} features included</span>
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {expanded && (
        <div className="bp-features-list">
          {(plan.features || []).map((feature, i) => (
            <div key={i} className="bp-feature-item">
              <CheckCircle2 size={12} color="var(--green)" />
              <span>{feature}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function InvoiceRow({ invoice }) {
  return (
    <div className="bp-invoice-row">
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Receipt size={16} color="var(--text-3)" />
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-0)" }}>
            {invoice.name || `Invoice ${invoice.id}`}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-3)" }}>
            {new Date(invoice.date).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
          </div>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text-0)" }}>
          ${invoice.amount}
        </span>
        <span className={`bp-invoice-status bp-invoice-status--${invoice.status}`}>
          {invoice.status === "paid" ? "Paid" : invoice.status === "pending" ? "Pending" : "Failed"}
        </span>
        <button className="bp-download-btn">
          <Download size={12} /> PDF
        </button>
      </div>
    </div>
  );
}

export default function BillingPage() {
  const navigate = useNavigate();
  const [me, setMe] = useState(null);
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [upgrading, setUpgrading] = useState(null);
  const [error, setError] = useState("");
  const [billingCycle, setBillingCycle] = useState("monthly");

  useEffect(() => {
    Promise.all([fetchBillingMe(), fetchPlans()])
      .then(([meRes, plansRes]) => {
        setMe(meRes);
        setPlans(plansRes.plans || []);
      })
      .catch(() => setError("Could not load billing information."))
      .finally(() => setLoading(false));
  }, []);

  const handleUpgrade = async (planId) => {
    setUpgrading(planId);
    try {
      const res = await createCheckout(
        planId,
        `${window.location.origin}/billing?success=1`,
        `${window.location.origin}/billing?cancelled=1`,
      );
      if (res.checkout_url) window.location.href = res.checkout_url;
    } catch {
      setError("Could not start checkout. Please try again.");
    } finally {
      setUpgrading(null);
    }
  };

  const css = `
    .bp-page { min-height: 100vh; background: var(--bg); padding: 32px; max-width: 1100px; margin: 0 auto; }
    .bp-back { display: inline-flex; align-items: center; gap: 6px; font-size: 12px;
      color: var(--text-2); cursor: pointer; border: none; background: none; margin-bottom: 24px; padding: 0; }
    .bp-back:hover { color: var(--text-0); }

    /* Header */
    .bp-header { margin-bottom: 32px; }
    .bp-title { font-size: 24px; font-weight: 800; color: var(--text-0); margin-bottom: 4px; }
    .bp-sub { font-size: 14px; color: var(--text-2); }

    /* Error */
    .bp-err { display: flex; align-items: center; gap: 8px; font-size: 13px;
      color: var(--red); background: var(--red-dim); border: 1px solid var(--red);
      border-radius: var(--radius-md); padding: 12px 16px; margin-bottom: 24px; }

    /* Billing Toggle */
    .bp-cycle-toggle { display: flex; align-items: center; gap: 8px; margin-bottom: 24px;
      background: var(--surface-1); border: 1px solid var(--border); border-radius: 99px; padding: 4px; width: fit-content; }
    .bp-cycle-btn { padding: 6px 16px; border-radius: 99px; border: none; background: none;
      font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s; color: var(--text-2); }
    .bp-cycle-btn--active { background: var(--accent); color: #fff; }
    .bp-save-badge { font-size: 10px; background: var(--green-dim); color: var(--green);
      padding: 2px 8px; border-radius: 99px; font-weight: 600; }

    /* Plans Grid */
    .bp-plans-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 32px; }

    /* Plan Card */
    .bp-plan-card { border-radius: var(--radius-lg); padding: 20px; position: relative; transition: all 0.2s; }
    .bp-plan-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-lg); }
    .bp-popular-badge { position: absolute; top: -10px; left: 50%; transform: translateX(-50%);
      background: var(--gradient-primary); color: #fff; font-size: 10px; font-weight: 700;
      padding: 4px 12px; border-radius: 99px; white-space: nowrap; display: flex; align-items: center; gap: 4px; }
    .bp-plan-header { display: flex; gap: 12px; margin-bottom: 16px; }
    .bp-plan-icon { width: 48px; height: 48px; border-radius: var(--radius-md); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
    .bp-plan-name { font-size: 16px; font-weight: 700; color: var(--text-0); }
    .bp-plan-price { display: flex; align-items: baseline; gap: 2px; margin-top: 4px; }
    .bp-current-badge { display: flex; align-items: center; gap: 6px; padding: 8px 14px; background: var(--green-dim);
      color: var(--green); border-radius: var(--radius-md); font-size: 12px; font-weight: 600; margin-bottom: 12px; }
    .bp-upgrade-btn { width: 100%; display: flex; align-items: center; justify-content: center; gap: 6px;
      padding: 10px 16px; border-radius: var(--radius-md); font-size: 13px; font-weight: 600; cursor: pointer; margin-bottom: 12px; transition: all 0.2s; }
    .bp-upgrade-btn:hover:not(:disabled) { filter: brightness(1.1); transform: translateY(-1px); }
    .bp-upgrade-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .bp-free-info { text-align: center; padding: 10px; font-size: 12px; color: var(--text-3); margin-bottom: 12px; }
    .bp-features-toggle { width: 100%; display: flex; align-items: center; justify-content: space-between;
      padding: 8px; background: var(--surface-2); border: none; border-radius: var(--radius-sm); cursor: pointer; font-size: 11px; color: var(--text-2); }
    .bp-features-toggle:hover { background: var(--surface-3); }
    .bp-features-list { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; }
    .bp-feature-item { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; color: var(--text-1); }
    .bp-feature-item svg { flex-shrink: 0; margin-top: 2px; }

    /* Usage Section */
    .bp-section { margin-bottom: 32px; }
    .bp-section-title { font-size: 14px; font-weight: 700; color: var(--text-0); margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
    .bp-usage-card { background: var(--surface-1); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 24px; }
    .bp-tier-info { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; padding-bottom: 20px; border-bottom: 1px solid var(--border); }
    .bp-tier-icon { width: 56px; height: 56px; border-radius: var(--radius-lg); display: flex; align-items: center; justify-content: center; }
    .bp-tier-name { font-size: 18px; font-weight: 700; color: var(--text-0); }
    .bp-tier-renewal { font-size: 12px; color: var(--text-3); margin-top: 2px; }
    .bp-reset-info { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-2); background: var(--surface-2); padding: 4px 10px; border-radius: 99px; }

    /* Payment Section */
    .bp-payment-card { background: var(--surface-1); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 20px; }
    .bp-payment-method { display: flex; align-items: center; gap: 12px; }
    .bp-card-icon { width: 48px; height: 32px; background: var(--surface-2); border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center; }
    .bp-card-number { font-size: 14px; fontWeight: 600; color: var(--text-0); }
    .bp-card-expiry { font-size: 12px; color: var(--text-3); }
    .bp-change-btn { margin-left: auto; padding: 6px 14px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 12px; font-weight: 600; cursor: pointer; color: var(--text-1); }

    /* Invoices */
    .bp-invoices-card { background: var(--surface-1); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; }
    .bp-invoice-row { display: flex; align-items: center; justify-content: space-between; padding: 14px 20px; border-bottom: 1px solid var(--border); }
    .bp-invoice-row:last-child { border-bottom: none; }
    .bp-invoice-status { font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 99px; }
    .bp-invoice-status--paid { background: var(--green-dim); color: var(--green); }
    .bp-invoice-status--pending { background: var(--amber-dim); color: var(--amber); }
    .bp-invoice-status--failed { background: var(--red-dim); color: var(--red); }
    .bp-download-btn { display: flex; align-items: center; gap: 4px; padding: 4px 10px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 11px; cursor: pointer; color: var(--text-2); }

    /* Info Box */
    .bp-info-box { display: flex; gap: 12px; padding: 16px; background: var(--accent-dim); border: 1px solid var(--border-glass); border-radius: var(--radius-md); margin-top: 16px; }
    .bp-info-box svg { flex-shrink: 0; color: var(--accent); }
    .bp-info-box p { font-size: 12px; color: var(--text-1); margin: 0; line-height: 1.6; }

    /* Responsive */
    @media (max-width: 768px) {
      .bp-page { padding: 20px; }
      .bp-plans-grid { grid-template-columns: 1fr; }
    }
  `;

  if (loading) {
    return (
      <div className="bp-page">
        <button className="bp-back" onClick={() => navigate(-1)}>
          <ArrowLeft size={13} /> Back
        </button>
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div style={{ height: 32, width: 200, background: "var(--surface-2)", borderRadius: 8 }} />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16 }}>
            {[1, 2, 3].map(i => (
              <div key={i} style={{ height: 280, background: "var(--surface-2)", borderRadius: 16 }} />
            ))}
          </div>
        </div>
      </div>
    );
  }

  const currentTier = me?.tier || "free";
  const usage = me?.usage || {};
  const limits = me?.limits || {};
  const tierColor = TIER_COLORS[currentTier] || "#6b7280";
  const nextReset = me?.next_billing_date ? new Date(me.next_billing_date) : null;

  const sampleInvoices = [
    { id: "INV-001", name: "Pro Plan - March 2026", date: "2026-03-01", amount: "29.00", status: "paid" },
    { id: "INV-002", name: "Pro Plan - February 2026", date: "2026-02-01", amount: "29.00", status: "paid" },
    { id: "INV-003", name: "Pro Plan - January 2026", date: "2026-01-01", amount: "29.00", status: "paid" },
  ];

  return (
    <>
      <style>{css}</style>
      <div className="bp-page">
        <button className="bp-back" onClick={() => navigate(-1)}>
          <ArrowLeft size={13} /> Back
        </button>

        <div className="bp-header">
          <h1 className="bp-title">Billing & Subscription</h1>
          <p className="bp-sub">Manage your plan, track usage, and view invoices</p>
        </div>

        {error && <div className="bp-err"><AlertCircle size={14} /> {error}</div>}

        {/* Billing Cycle Toggle */}
        <div className="bp-cycle-toggle">
          <button className={`bp-cycle-btn ${billingCycle === "monthly" ? "bp-cycle-btn--active" : ""}`}
            onClick={() => setBillingCycle("monthly")}>
            Monthly
          </button>
          <button className={`bp-cycle-btn ${billingCycle === "annual" ? "bp-cycle-btn--active" : ""}`}
            onClick={() => setBillingCycle("annual")}>
            Annual
          </button>
          <span className="bp-save-badge">Save 20%</span>
        </div>

        {/* Plans Grid */}
        <div className="bp-section">
          <h2 className="bp-section-title">
            <Zap size={16} style={{ color: "var(--accent)" }} />
            Choose Your Plan
          </h2>
          <div className="bp-plans-grid">
            {plans.map(plan => (
              <PlanCard
                key={plan.id}
                plan={plan}
                isCurrent={plan.id === currentTier}
                onUpgrade={handleUpgrade}
                upgrading={upgrading}
                accentColor={tierColor}
              />
            ))}
          </div>
        </div>

        {/* Current Usage */}
        <div className="bp-section">
          <h2 className="bp-section-title">
            <BarChart2 size={16} style={{ color: "var(--accent)" }} />
            Current Usage
          </h2>
          <div className="bp-usage-card">
            <div className="bp-tier-info">
              <div className="bp-tier-icon" style={{ background: `${tierColor}15`, border: `1px solid ${tierColor}30` }}>
                {React.createElement(TIER_ICONS[currentTier] || Shield, { size: 24, color: tierColor })}
              </div>
              <div>
                <div className="bp-tier-name" style={{ color: tierColor }}>
                  {currentTier.charAt(0).toUpperCase() + currentTier.slice(1)} Plan
                </div>
                {nextReset && (
                  <div className="bp-tier-renewal">
                    Renews {nextReset.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
                  </div>
                )}
              </div>
              <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
                <span className="bp-reset-info">
                  <Clock size={12} />
                  Resets {me?.billing_period === "monthly" ? "monthly" : "annually"}
                </span>
              </div>
            </div>

            <UsageBar label="Datasets" used={usage.datasets || 0} limit={limits.max_datasets} icon={Database} color={tierColor} />
            <UsageBar label="Rows per upload" used={usage.max_rows_used || 0} limit={limits.max_rows} icon={BarChart2} color={tierColor} />
            <UsageBar label="AI calls today" used={usage.ai_calls_today || 0} limit={limits.ai_calls_per_day} icon={Bot} color={tierColor} />
            <UsageBar label="Total storage" used={usage.storage_used || 0} limit={limits.max_storage} icon={Database} color={tierColor} />
            <UsageBar label="Team members" used={usage.team_members || 1} limit={limits.max_team_members} icon={Users} color={tierColor} />
          </div>
        </div>

        {/* Payment Method */}
        <div className="bp-section">
          <h2 className="bp-section-title">
            <CreditCard size={16} style={{ color: "var(--accent)" }} />
            Payment Method
          </h2>
          <div className="bp-payment-card">
            <div className="bp-payment-method">
              <div className="bp-card-icon">
                <CreditCard size={20} color="var(--text-2)" />
              </div>
              <div>
                <div className="bp-card-number">•••• •••• •••• 4242</div>
                <div className="bp-card-expiry">Expires 12/28</div>
              </div>
              <button className="bp-change-btn">Change</button>
            </div>
            <div className="bp-info-box">
              <Info size={16} />
              <p>Your payment is secured with Stripe. We never store your full card details.</p>
            </div>
          </div>
        </div>

        {/* Invoice History */}
        <div className="bp-section">
          <h2 className="bp-section-title">
            <Receipt size={16} style={{ color: "var(--accent)" }} />
            Invoice History
          </h2>
          <div className="bp-invoices-card">
            {sampleInvoices.map(invoice => (
              <InvoiceRow key={invoice.id} invoice={invoice} />
            ))}
          </div>
        </div>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </>
  );
}
