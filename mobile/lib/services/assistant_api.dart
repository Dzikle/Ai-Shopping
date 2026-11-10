import '../models/assistant_models.dart';
import 'api_service.dart';

/// Guest-safe M13 assistant transport.
///
/// A dedicated [ApiService] instance is used (the assistant call can take
/// longer than plain catalog reads) and no credentials are ever attached.
/// The server only proposes changes - this client never mutates state.
abstract class AssistantApi {
  Future<AssistantTurn> sendTurn(AssistantTurnRequest request);
}

class HttpAssistantApi implements AssistantApi {
  HttpAssistantApi({ApiService? service})
      : _service = service ?? ApiService();

  final ApiService _service;

  @override
  Future<AssistantTurn> sendTurn(AssistantTurnRequest request) async {
    final json = await _service.post(
      '/api/v1/assistant/turn',
      body: request.toJson(),
    );
    return AssistantTurn.fromJson(json as Map<String, dynamic>);
  }
}
