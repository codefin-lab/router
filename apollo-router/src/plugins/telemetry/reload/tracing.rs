//! Trace provider construction
//!
//! This module provides tools for building OpenTelemetry tracer providers from router configuration.
//!
//! ## Purpose
//!
//! The [`TracingBuilder`] constructs a tracer provider that handles distributed tracing across
//! multiple backends (OTLP, Datadog, Zipkin, Apollo). It also configures trace propagation to
//! ensure trace context is properly propagated across service boundaries.
//!
//! ## Configurator Pattern
//!
//! The [`TracingConfigurator`] trait allows different trace exporters to contribute span processors
//! to the builder. Each exporter (OTLP, Datadog, Zipkin, Apollo) implements this trait to add its
//! specific span processing logic.
//!
//! ## Propagation
//!
//! The [`create_propagator`] function builds a composite propagator supporting multiple trace
//! context formats (W3C Trace Context, Jaeger, Zipkin, Datadog, AWS X-Ray). This allows the router
//! to interoperate with services using different tracing systems.

use opentelemetry::propagation::TextMapCompositePropagator;
use opentelemetry::propagation::TextMapPropagator;
use opentelemetry_sdk::trace::SdkTracerProvider;
use opentelemetry_sdk::trace::SpanProcessor;
use tower::BoxError;

use crate::plugins::telemetry::CustomTraceIdPropagator;
use crate::plugins::telemetry::config::Conf;
use crate::plugins::telemetry::config::Propagation;
use crate::plugins::telemetry::config::Tracing;
use crate::plugins::telemetry::config::TracingCommon;
use crate::plugins::telemetry::config_new::spans::Spans;

/// Builder for constructing OpenTelemetry tracer providers with multiple exporters
pub(crate) struct TracingBuilder<'a> {
    common: &'a TracingCommon,
    spans: &'a Spans,
    builder: opentelemetry_sdk::trace::TracerProviderBuilder,
}

impl<'a> TracingBuilder<'a> {
    pub(crate) fn new(config: &'a Conf) -> Self {
        let common = &config.exporters.tracing.common;
        Self {
            common,
            spans: &config.instrumentation.spans,
            builder: common.configure_tracer_provider_builder(
                opentelemetry_sdk::trace::SdkTracerProvider::builder(),
            ),
        }
    }

    pub(crate) fn configure<T: TracingConfigurator>(&mut self, config: &T) -> Result<(), BoxError> {
        if config.is_enabled() {
            return config.configure(self);
        }
        Ok(())
    }

    pub(crate) fn tracing_common(&self) -> &TracingCommon {
        self.common
    }

    pub(crate) fn spans(&self) -> &Spans {
        self.spans
    }

    pub(crate) fn with_span_processor<T: SpanProcessor + 'static>(&mut self, span_processor: T) {
        let builder = std::mem::take(&mut self.builder);
        self.builder = builder.with_span_processor(span_processor);
    }

    pub(crate) fn build(self) -> SdkTracerProvider {
        self.builder.build()
    }
}

pub(crate) fn create_propagator(
    propagation: &Propagation,
    tracing: &Tracing,
) -> TextMapCompositePropagator {
    let mut propagators: Vec<Box<dyn TextMapPropagator + Send + Sync + 'static>> = Vec::new();

    if tracing.is_jaeger_propagation_enabled() {
        propagators.push(Box::<opentelemetry_jaeger_propagator::Propagator>::default());
    }
    if tracing.is_baggage_propagation_enabled() {
        propagators.push(Box::<BoundedBaggagePropagator>::default());
    }
    if tracing.is_trace_context_propagation_enabled() {
        propagators.push(Box::<opentelemetry_sdk::propagation::TraceContextPropagator>::default());
    }
    if tracing.is_zipkin_propagation_enabled() {
        propagators.push(Box::<opentelemetry_zipkin::Propagator>::default());
    }
    if tracing.is_datadog_propagation_enabled() {
        if tracing.is_jaeger_propagation_enabled()
            || tracing.is_trace_context_propagation_enabled()
            || tracing.is_zipkin_propagation_enabled()
            || tracing.is_aws_xray_propagation_enabled()
        {
            if tracing.datadog.enabled && propagation.datadog.unwrap_or(false) {
                tracing::warn!(
                    "if the datadog exporter is enabled and any other propagator except for baggage is enabled, the datadog propagator should be disabled to avoid trace id conflicts"
                );
            } else if let Some(true) = propagation.datadog {
                tracing::warn!(
                    "datadog propagation should not be used with any other propagator except for baggage to avoid trace id conflicts"
                );
            } else if propagation.datadog.is_none() {
                tracing::warn!(
                    "datadog propagation should be explicitly disabled if the datadog exporter is enabled and any propagator other than baggage is enabled to avoid trace id conflicts"
                );
            }
        }

        propagators.push(Box::<
            crate::plugins::telemetry::tracing::datadog_exporter::DatadogPropagator,
        >::default());
    }
    if propagation.aws_xray {
        propagators.push(Box::<opentelemetry_aws::trace::XrayPropagator>::default());
    }

    // This propagator MUST come last because the user is trying to override the default behavior of the
    // other propagators.
    if let Some(from_request_header) = &propagation.request.header_name {
        propagators.push(Box::new(CustomTraceIdPropagator::new(
            from_request_header.to_string(),
            propagation.request.format.clone(),
        )));
    }
    TextMapCompositePropagator::new(propagators)
}

/// Trait for trace exporters to contribute to tracer provider construction
pub(crate) trait TracingConfigurator {
    fn config(conf: &Conf) -> &Self;
    fn is_enabled(&self) -> bool;
    fn configure(&self, builder: &mut TracingBuilder) -> Result<(), BoxError>;
}

// CVE-2026-48504: bound untrusted input before SDK 0.31 parses or allocates it.
// Keep this guard until the coupled SDK/exporter stack adopts the upstream fix.
#[derive(Debug, Default)]
struct BoundedBaggagePropagator(opentelemetry_sdk::propagation::BaggagePropagator);

impl TextMapPropagator for BoundedBaggagePropagator {
    fn inject_context(
        &self,
        cx: &opentelemetry::Context,
        injector: &mut dyn opentelemetry::propagation::Injector,
    ) {
        self.0.inject_context(cx, injector);
    }

    fn extract_with_context(
        &self,
        cx: &opentelemetry::Context,
        extractor: &dyn opentelemetry::propagation::Extractor,
    ) -> opentelemetry::Context {
        if let Some(value) = extractor.get("baggage") {
            if value.len() > 8192 || value.split(',').take(65).count() > 64 {
                return cx.clone();
            }
        }
        self.0.extract_with_context(cx, extractor)
    }

    fn fields(&self) -> opentelemetry::propagation::text_map_propagator::FieldIter<'_> {
        self.0.fields()
    }
}

#[cfg(test)]
mod bounded_baggage_tests {
    use super::*;
    use opentelemetry::baggage::BaggageExt;
    use std::collections::HashMap;

    #[test]
    fn accepts_normal_baggage_and_preserves_injection() {
        let p = BoundedBaggagePropagator::default();
        let headers = HashMap::from([("baggage".to_string(), "team=wealth".to_string())]);
        let cx = p.extract(&headers);
        assert_eq!(cx.baggage().get("team").unwrap().as_str(), "wealth");
        let mut output = HashMap::new();
        p.inject_context(&cx, &mut output);
        assert_eq!(output.get("baggage").unwrap(), "team=wealth");
    }

    #[test]
    fn rejects_oversized_bytes_and_preserves_existing_context() {
        let p = BoundedBaggagePropagator::default();
        let cx = opentelemetry::Context::new()
            .with_baggage([opentelemetry::KeyValue::new("existing", "value")]);
        for value in [
            format!("x={}", "a".repeat(8191)),
            format!("x={}", "é".repeat(4096)),
        ] {
            let headers = HashMap::from([("baggage".to_string(), value)]);
            let result = p.extract_with_context(&cx, &headers);
            assert!(result.baggage().get("x").is_none());
            assert!(result.baggage().get("existing").is_some());
        }
    }

    #[test]
    fn accepts_64_members_and_rejects_65() {
        let p = BoundedBaggagePropagator::default();
        for count in [64, 65] {
            let value = (0..count)
                .map(|i| format!("k{i}=v"))
                .collect::<Vec<_>>()
                .join(",");
            let headers = HashMap::from([("baggage".to_string(), value)]);
            assert_eq!(
                p.extract(&headers).baggage().len(),
                if count == 64 { 64 } else { 0 }
            );
        }
    }

    #[test]
    fn invalid_baggage_does_not_discard_trace_context() {
        use opentelemetry::trace::TraceContextExt;
        let p = TextMapCompositePropagator::new(vec![
            Box::<BoundedBaggagePropagator>::default(),
            Box::<opentelemetry_sdk::propagation::TraceContextPropagator>::default(),
        ]);
        let headers = HashMap::from([
            ("baggage".to_string(), "x".repeat(8193)),
            (
                "traceparent".to_string(),
                "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01".to_string(),
            ),
        ]);
        let cx = p.extract(&headers);
        assert!(cx.span().span_context().is_valid());
        assert_eq!(cx.baggage().len(), 0);
    }
}
