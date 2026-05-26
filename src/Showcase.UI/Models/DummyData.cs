namespace Showcase.UI.Models;

/// <summary>
/// 事例 1 件分の表示用データ。Phase 6 で RAG/SQLite 由来の実データに差し替える。
/// </summary>
/// <param name="CaseId">事例 ID（例: "case001"）。</param>
/// <param name="Title">タイトル。</param>
/// <param name="SubTitle">サブタイトル。</param>
/// <param name="Year">導入年。</param>
/// <param name="Category">カテゴリ。</param>
/// <param name="Description">説明文。</param>
/// <param name="Tags">タグ一覧。</param>
public record CaseItem(
    string CaseId,
    string Title,
    string SubTitle,
    int Year,
    string Category,
    string Description,
    IReadOnlyList<string> Tags);

/// <summary>
/// Phase 4 骨組み用のダミーデータ供給。
/// TODO(Phase 6): RAG 検索結果・SQLite メタデータ DB からの取得に置き換える。
/// </summary>
public static class DummyData
{
    private static readonly IReadOnlyList<CaseItem> Cases = new List<CaseItem>
    {
        new("case001",
            "大型LEDサイネージ導入事例",
            "エントランスを彩る大画面ビジュアル",
            2024,
            "LEDサイネージ",
            "ご来館の皆様をお迎えするエントランスに、高輝度の大型LEDディスプレイを設置した事例です。"
            + "OSMIL による表示制御で、時間帯や来場者の動きに応じたコンテンツ切り替えを実現しました。"
            + "屋内外の明るさ変化にも自動で追従し、常に最適な視認性を保ちます。",
            new[] { "LED", "大型", "エントランス", "OSMIL" }),

        new("case002",
            "インタラクティブタッチサイネージ",
            "触れて楽しむ案内システム",
            2024,
            "タッチUI",
            "来場者自身が画面に触れて情報を引き出せる、対話型のタッチサイネージ事例です。"
            + "直感的な操作で施設案内やフロアマップを表示し、待ち時間のストレスを軽減します。"
            + "多人数での同時操作にも対応しています。",
            new[] { "タッチ", "インタラクティブ", "案内" }),

        new("case003",
            "ハイブリッドプロジェクション",
            "空間全体を映像で包む演出",
            2026,
            "プロジェクション",
            "壁面と床面を組み合わせたプロジェクションマッピングにより、空間全体を映像で演出した事例です。"
            + "複数プロジェクターのエッジブレンディングを OSMIL で統合制御し、継ぎ目のない大規模投影を実現しました。",
            new[] { "プロジェクション", "マッピング", "空間演出", "OSMIL" }),

        new("case004",
            "多言語音声解説システム",
            "音声で導く多言語ガイド",
            2024,
            "多言語・音声",
            "音声入力に応じて多言語の解説を提示する、インバウンド対応の解説システム事例です。"
            + "ローカル処理で完結するため、ネットワーク環境に依存せず安定して動作します。",
            new[] { "多言語", "音声", "インバウンド", "オフライン" }),

        new("case005",
            "デジタルアーカイブ展示",
            "貴重資料をデジタルで未来へ",
            2025,
            "インタラクティブ展示",
            "貴重な資料を高精細にデジタル化し、来場者が自由に閲覧・拡大できるアーカイブ展示の事例です。"
            + "原資料を傷めることなく、細部までじっくりご覧いただけます。",
            new[] { "アーカイブ", "高精細", "展示", "デジタル化" }),
    };

    /// <summary>全事例を返す（検索結果一覧用）。</summary>
    public static IReadOnlyList<CaseItem> GetCases() => Cases;

    /// <summary>ID 指定で 1 件取得。該当なしは null。</summary>
    public static CaseItem? GetCaseById(string caseId) =>
        Cases.FirstOrDefault(c => c.CaseId == caseId);

    /// <summary>
    /// 指定事例の関連事例を返す（自身を除外し、最大 <see cref="Constants.RelatedCaseMaxCount"/> 件）。
    /// TODO(Phase 6): ベクトル類似度に基づく関連抽出へ置き換える。
    /// </summary>
    public static IReadOnlyList<CaseItem> GetRelatedCases(string caseId) =>
        Cases.Where(c => c.CaseId != caseId)
             .Take(Constants.RelatedCaseMaxCount)
             .ToList();
}
