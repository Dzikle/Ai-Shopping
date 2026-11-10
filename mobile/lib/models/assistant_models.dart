import 'api_models.dart';

/// Typed contract for the M13 guest assistant route
/// `POST /api/v1/assistant/turn`.
///
/// Mirrors `backend_py/app/schemas/assistant.py`. The server only *proposes*
/// basket changes; nothing applies until the user confirms in the app, and
/// totals shown here always come from the deterministic server optimizer.

/// Server-side limits echoed in each turn; enforced client-side as a courtesy.
class AssistantLimits {
  const AssistantLimits({
    this.messageMaxChars = 500,
    this.conversationContextMaxEntries = 6,
    this.currentBasketMaxItems = 20,
    this.maxItemsPerTurn = 8,
    this.maxToolCallsPerTurn = 10,
  });

  final int messageMaxChars;
  final int conversationContextMaxEntries;
  final int currentBasketMaxItems;
  final int maxItemsPerTurn;
  final int maxToolCallsPerTurn;

  factory AssistantLimits.fromJson(Map<String, dynamic>? json) => AssistantLimits(
        messageMaxChars: _int(json?['messageMaxChars']) ?? 500,
        conversationContextMaxEntries:
            _int(json?['conversationContextMaxEntries']) ?? 6,
        currentBasketMaxItems: _int(json?['currentBasketMaxItems']) ?? 20,
        maxItemsPerTurn: _int(json?['maxItemsPerTurn']) ?? 8,
        maxToolCallsPerTurn: _int(json?['maxToolCallsPerTurn']) ?? 10,
      );
}

/// A prior chat entry echoed to the server (bounded to 6 entries).
class AssistantConversationEntry {
  const AssistantConversationEntry({required this.role, required this.content});

  factory AssistantConversationEntry.fromJson(Map<String, dynamic> json) =>
      AssistantConversationEntry(
        role: json['role'] is String ? json['role'] as String : 'user',
        content: json['content'] is String ? json['content'] as String : '',
      );

  final String role; // user | assistant
  final String content;

  Map<String, dynamic> toJson() => {'role': role, 'content': content};
}

/// Server-side preferences passed with each turn.
class AssistantPreferences {
  const AssistantPreferences({
    this.city,
    this.maxStores = 2,
    this.allowSubstitutes = false,
  });

  final String? city;
  final int maxStores; // 1..3
  final bool allowSubstitutes;

  Map<String, dynamic> toJson() => {
        if (city != null && city!.isNotEmpty) 'city': city,
        'maxStores': maxStores,
        'allowSubstitutes': allowSubstitutes,
      };
}

/// The current local basket echoed as context; never mutated by the server.
class AssistantBasketEchoItem {
  const AssistantBasketEchoItem({
    required this.label,
    required this.quantity,
    required this.unit,
    this.canonicalProductId,
    this.retailerProductId,
  });

  factory AssistantBasketEchoItem.fromBasketItem(BasketItem item) =>
      AssistantBasketEchoItem(
        label: item.label,
        quantity: item.quantity,
        unit: item.unit,
        canonicalProductId: item.canonicalProductId,
        retailerProductId: item.retailerProductId,
      );

  final String label;
  final double quantity;
  final String unit;
  final int? canonicalProductId;
  final int? retailerProductId;

  Map<String, dynamic> toJson() => {
        'label': label,
        'quantity': quantity,
        'unit': unit,
        if (canonicalProductId != null) 'canonicalProductId': canonicalProductId,
        if (retailerProductId != null) 'retailerProductId': retailerProductId,
      };
}

/// A user decision for an ambiguous item, queued for the next turn.
class AssistantCandidateSelection {
  const AssistantCandidateSelection({
    required this.itemLabel,
    required this.query,
    required this.candidateId,
    required this.quantity,
    required this.unit,
  });

  final String itemLabel;
  final String query;
  final String candidateId;
  final double quantity;
  final String unit;

  Map<String, dynamic> toJson() => {
        'itemLabel': itemLabel,
        'query': query,
        'candidateId': candidateId,
        'quantity': quantity,
        'unit': unit,
      };
}

/// Request body for `/api/v1/assistant/turn`.
class AssistantTurnRequest {
  const AssistantTurnRequest({
    required this.message,
    this.locale = 'mk',
    this.conversationContext = const [],
    this.currentBasket = const [],
    this.preferences,
    this.candidateSelections = const [],
  });

  final String? message; // null for explicit selection turns
  final String locale; // mk | en
  final List<AssistantConversationEntry> conversationContext;
  final List<AssistantBasketEchoItem> currentBasket;
  final AssistantPreferences? preferences;
  final List<AssistantCandidateSelection> candidateSelections;

  Map<String, dynamic> toJson() => {
        if (message != null) 'message': message,
        'locale': locale,
        if (conversationContext.isNotEmpty)
          'conversationContext':
              conversationContext.map((e) => e.toJson()).toList(growable: false),
        if (currentBasket.isNotEmpty)
          'currentBasket':
              currentBasket.map((e) => e.toJson()).toList(growable: false),
        if (preferences != null) 'preferences': preferences!.toJson(),
        if (candidateSelections.isNotEmpty)
          'candidateSelections':
              candidateSelections.map((e) => e.toJson()).toList(growable: false),
      };
}

/// Model/provider provenance of a turn.
class AssistantProviderInfo {
  const AssistantProviderInfo({
    required this.id,
    this.model,
    required this.isMock,
    required this.configured,
  });

  factory AssistantProviderInfo.fromJson(Map<String, dynamic>? json) =>
      AssistantProviderInfo(
        id: json?['id'] is String ? json!['id'] as String : 'unknown',
        model: json?['model'] is String ? json!['model'] as String : null,
        isMock: json?['isMock'] == true,
        configured: json?['configured'] == true,
      );

  final String id;
  final String? model;
  final bool isMock;
  final bool configured;
}

/// A catalog option offered when an item is ambiguous.
class AssistantChoiceOption {
  const AssistantChoiceOption({
    required this.candidateId,
    required this.retailerSlug,
    required this.listingName,
    required this.priceCurrentMkd,
    this.canonicalName,
    this.normalizedSize,
    this.unitPrice,
    this.unitLabel,
    this.isSubstituteCandidate = false,
    this.matchConfidence,
    this.publishedTs,
    this.sourceUrl,
  });

  factory AssistantChoiceOption.fromJson(Map<String, dynamic> json) =>
      AssistantChoiceOption(
        candidateId: json['candidateId'] is String ? json['candidateId'] as String : '',
        retailerSlug: json['retailerSlug'] is String ? json['retailerSlug'] as String : '',
        listingName: json['listingName'] is String ? json['listingName'] as String : '',
        priceCurrentMkd: _double(json['priceCurrentMkd']),
        canonicalName: _string(json['canonicalName']),
        normalizedSize: _string(json['normalizedSize']),
        unitPrice: _double(json['unitPrice']),
        unitLabel: _string(json['unitLabel']),
        isSubstituteCandidate: json['isSubstituteCandidate'] == true,
        matchConfidence: _double(json['matchConfidence']),
        publishedTs: _string(json['publishedTs']),
        sourceUrl: _string(json['sourceUrl']),
      );

  final String candidateId;
  final String retailerSlug;
  final String listingName;
  final double? priceCurrentMkd;
  final String? canonicalName;
  final String? normalizedSize;
  final double? unitPrice;
  final String? unitLabel;
  final bool isSubstituteCandidate;
  final double? matchConfidence;
  final String? publishedTs;
  final String? sourceUrl;
}

/// One ambiguous item needing an explicit user pick.
class AssistantChoice {
  const AssistantChoice({
    required this.itemLabel,
    required this.query,
    required this.reason,
    required this.options,
    this.requestedQuantity,
    this.requestedUnit,
  });

  factory AssistantChoice.fromJson(Map<String, dynamic> json) => AssistantChoice(
        itemLabel: json['itemLabel'] is String ? json['itemLabel'] as String : '',
        query: json['query'] is String ? json['query'] as String : '',
        reason: json['reason'] is String ? json['reason'] as String : 'unknown',
        requestedQuantity: _double(json['requestedQuantity']),
        requestedUnit: _string(json['requestedUnit']),
        options: (json['options'] as List? ?? const [])
            .whereType<Map>()
            .map((o) => AssistantChoiceOption.fromJson(Map<String, dynamic>.from(o)))
            .toList(growable: false),
      );

  final String itemLabel;
  final String query;
  final String reason; // multiple_products | multiple_unverified | no_in_stock_offers
  final double? requestedQuantity;
  final String? requestedUnit;
  final List<AssistantChoiceOption> options;
}

/// A catalog-verified proposal awaiting explicit confirmation.
class AssistantProposal {
  const AssistantProposal({
    required this.changeType,
    required this.itemLabel,
    required this.quantity,
    required this.unit,
    required this.verifiedIdentity,
    this.canonicalProductId,
    this.retailerProductId,
    this.listingName,
    this.retailerSlug,
    this.priceCurrentMkd,
    this.oldQuantity,
    this.oldUnit,
    this.publishedTs,
    this.sourceUrl,
  });

  factory AssistantProposal.fromJson(Map<String, dynamic> json) =>
      AssistantProposal(
        changeType: json['changeType'] is String ? json['changeType'] as String : 'add',
        itemLabel: json['itemLabel'] is String ? json['itemLabel'] as String : '',
        quantity: _double(json['quantity']) ?? 1,
        unit: json['unit'] is String ? json['unit'] as String : 'pack',
        verifiedIdentity: json['verifiedIdentity'] == true,
        canonicalProductId: _int(json['canonicalProductId']),
        retailerProductId: _int(json['retailerProductId']),
        listingName: _string(json['listingName']),
        retailerSlug: _string(json['retailerSlug']),
        priceCurrentMkd: _double(json['priceCurrentMkd']),
        oldQuantity: _double(json['oldQuantity']),
        oldUnit: _string(json['oldUnit']),
        publishedTs: _string(json['publishedTs']),
        sourceUrl: _string(json['sourceUrl']),
      );

  final String changeType; // add | replace_quantity
  final String itemLabel;
  final double quantity;
  final String unit;
  final bool verifiedIdentity;
  final int? canonicalProductId;
  final int? retailerProductId;
  final String? listingName;
  final String? retailerSlug;
  final double? priceCurrentMkd;
  final double? oldQuantity;
  final String? oldUnit;
  final String? publishedTs;
  final String? sourceUrl;

  bool get isAdd => changeType == 'add';
  bool get isReplace => changeType == 'replace_quantity';
}

/// An item that could not be grounded in the catalog.
class AssistantUnresolved {
  const AssistantUnresolved({required this.label, required this.reason});

  factory AssistantUnresolved.fromJson(Map<String, dynamic> json) =>
      AssistantUnresolved(
        label: json['label'] is String ? json['label'] as String : '',
        reason: json['reason'] is String ? json['reason'] as String : 'unknown',
      );

  final String label;
  final String reason; // no_offers_found | search_failed | tool_budget_exhausted | ...
}

/// Bounded server-side optimization preview over the current basket plus the
/// proposed changes (`optimizationPreview` in the turn response). Display
/// only: applying proposals re-runs the full optimizer through the normal
/// basket service before any totals are treated as authoritative.
class AssistantPreview {
  const AssistantPreview({
    required this.totalItemsRequested,
    this.bestStoreName,
    this.bestRetailerSlug,
    this.bestTotalMkd,
    this.bestCoveredCount,
    this.bestTotalRequested,
    this.previewOnly = true,
  });

  factory AssistantPreview.fromJson(Map<String, dynamic> json) {
    final best = json['bestSingleStore'] as Map<String, dynamic>?;
    return AssistantPreview(
      totalItemsRequested: _int(json['totalItemsRequested']) ?? 0,
      bestStoreName: _string(best?['storeName']),
      bestRetailerSlug: _string(best?['retailerSlug']),
      bestTotalMkd: _double(best?['totalMkd']),
      bestCoveredCount: _int(best?['itemsCovered']),
      bestTotalRequested: _int(best?['totalItemsRequested']),
      previewOnly: json['previewOnly'] == true,
    );
  }

  final int totalItemsRequested;
  final String? bestStoreName;
  final String? bestRetailerSlug;
  final double? bestTotalMkd;
  final int? bestCoveredCount;
  final int? bestTotalRequested;
  final bool previewOnly;
}

/// One completed assistant turn (the full bounded response).
class AssistantTurn {
  const AssistantTurn({
    required this.requestId,
    required this.status,
    required this.assistantMessage,
    required this.provider,
    required this.warnings,
    this.limits = const AssistantLimits(),
    this.proposals = const [],
    this.choices = const [],
    this.unresolved = const [],
    this.preview,
  });

  factory AssistantTurn.fromJson(Map<String, dynamic> json) => AssistantTurn(
        requestId: json['requestId'] is String ? json['requestId'] as String : '',
        status: json['status'] is String ? json['status'] as String : 'ok',
        assistantMessage:
            json['assistantMessage'] is String ? json['assistantMessage'] as String : '',
        provider: AssistantProviderInfo.fromJson(
            json['provider'] as Map<String, dynamic>?),
        warnings: (json['warnings'] as List? ?? const [])
            .whereType<String>()
            .toList(growable: false),
        limits: AssistantLimits.fromJson(json['limits'] as Map<String, dynamic>?),
        proposals: (json['proposedBasketChanges'] as List? ?? const [])
            .whereType<Map>()
            .map((p) => AssistantProposal.fromJson(Map<String, dynamic>.from(p)))
            .toList(growable: false),
        choices: (json['candidateChoices'] as List? ?? const [])
            .whereType<Map>()
            .map((c) => AssistantChoice.fromJson(Map<String, dynamic>.from(c)))
            .toList(growable: false),
        unresolved: (json['unresolvedItems'] as List? ?? const [])
            .whereType<Map>()
            .map((u) => AssistantUnresolved.fromJson(Map<String, dynamic>.from(u)))
            .toList(growable: false),
        preview: json['optimizationPreview'] is Map
            ? AssistantPreview.fromJson(
                Map<String, dynamic>.from(json['optimizationPreview'] as Map))
            : null,
      );

  final String requestId;
  final String status; // ok | needs_clarification | model_unavailable | model_error | assistant_error
  final String assistantMessage;
  final AssistantProviderInfo provider;
  final List<String> warnings;
  final AssistantLimits limits;
  final List<AssistantProposal> proposals;
  final List<AssistantChoice> choices;
  final List<AssistantUnresolved> unresolved;
  final AssistantPreview? preview;

  bool get hasChoices => choices.isNotEmpty;
  bool get hasProposals => proposals.isNotEmpty;
  bool get needsClarification => status == 'needs_clarification';
  bool get isActionable => status == 'ok' || status == 'needs_clarification';
}

String? _string(dynamic value) => value is String ? value : null;
int? _int(dynamic value) => value is int ? value : (value is num ? value.toInt() : null);
double? _double(dynamic value) =>
    value is num ? value.toDouble() : (value is String ? double.tryParse(value) : null);
