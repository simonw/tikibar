// Load jQuery if it's not present on the window
if (!window.jQuery) {
    jQueryScriptTag = document.createElement('script');
    jQueryScriptTag.src = 'https://code.jquery.com/jquery-1.7.2.min.js';
    jQueryScriptTag.integrity = 'sha256-R7aNzoy2gFrVs+pNJ6+SokH04ppcEqJ0yFLkNGoFALQ=';
    jQueryScriptTag.crossOrigin = 'anonymous';
    jQueryScriptTag.onload = function() {
        start($);
    }
    document.body.appendChild(jQueryScriptTag);
} else {
    start(jQuery);
}

function extractDomain(url) {
    var originMatches = url.match(domainRegex);
    return originMatches && originMatches[3];
}

var domainRegex = /^(https?:\/\/)?([-\w]+\.)*([-\w]+\.(com|ca|co\.uk|ie|de|es|fr|it|nl|pt|sv|co\.nz|com\.au|hk|sg|in|com\.br))(\/.*)?$/;

function start($) {

    $(window).on('load', function() {
        // Poll until tikibar_host is available
        var interval = setInterval(function() {
            if (window.tikibar_host) {
                tikibar_host.send_performance_data();
                clearInterval(interval);
            }
        }, 100);
    });

    // set tikibar host on window
    $(function() {
        function TikibarHost(options) {
            if (this == window) {
                return new TikibarHost(options);
            }
            options = options || {};
            var attach = options.attach || document.body;

            $('#tikibar_iframe_container').remove();
            var div = $('<div id="tikibar_iframe_container"><iframe width="100%" height="100%"></iframe></div>');
            this.iframe = div.find('iframe')[0];
            this.container = div[0];
            div.height(60);
            div.find('iframe').height(60); // For mobile safari
            // We position absolute / zindex the iframe to prevent the box shadow
            // on the autocomplete box in the eventbrite header from overlapping the tikibar
            div.find('iframe').css({
                position: 'absolute',
                zIndex: 1000
            });
            div.find('iframe').attr('src', this.get_tikibar_url());
            div.prependTo(attach);
            $(attach).css({
                position: 'absolute',
                width: '100%',
                top: '60px',
                margin: 0
            });
            div.css({
                marginTop: '-60px'
            });

            // Recieve messages from the child frame
            window.addEventListener('message', this.recieve_message.bind(this));

            // Listen to jQuery Ajax calls
            $(document).bind('ajaxComplete', this.on_ajax_request.bind(this));

            // Listen to fetch() calls too
            var self = this;
            var original_fetch;
            if (window.fetch && window.Promise) {
                original_fetch = window.fetch;
                window.fetch = function(input, init) {
                    return original_fetch(input, init).then(function(response) {
                        var method = (init || {}).method || 'GET';
                        var correlation_id = response.headers.get('x-correlation-id');
                        var tiki_time = parseFloat(response.headers.get('x-tiki-time') || '0');
                        self.send_message({
                            'tiki_msg_type': 'ajax_request',
                            'url': input,
                            'verb': method, // GET or POST
                            'status_code': response.status,
                            'ms': tiki_time * 1000,
                            'correlation_id': correlation_id
                        });
                        return Promise.resolve(response);
                    });
                }
            }
        }

        TikibarHost.prototype.recieve_message = function(event) {
            var originDomain = extractDomain(event.origin);
            var currentDomain = extractDomain(location.host);
            var data = event.data;

            if (originDomain != currentDomain) {
                return;
            }
            if (typeof data === 'string') {
                data = JSON.parse(data);
            }
            if (data.tiki_msg_type == 'height') {
                $(this.container).add(this.iframe).height(data.height);
            }
            if (data.tiki_msg_type == 'hide') {
                $(this.container).remove();
            }
        }

        TikibarHost.prototype.send_message = function(msg) {
            this.iframe.contentWindow.postMessage(JSON.stringify(msg), '*');
        }

        TikibarHost.prototype.send_performance_data = function() {
            // Create a copy of window.performance.timings
            var copy = {};
            var ok = false;
            var timing = (window.performance && window.performance.timing) || {};
            $.each(timing, function(name, timestamp) {
                if (!$.isNumeric(timestamp)) {
                    return true; // Skip this one (e.g. toJSON on Firefox)
                }
                ok = true;
                copy[name] = timestamp;
            });
            if (ok) {
                this.send_message({
                    'tiki_msg_type': 'performance_timing',
                    'timing': copy
                });
            }
        }

        TikibarHost.prototype.get_tikibar_url = function() {
            var correlation_id = document.getElementsByName('correlation_id')[0].getAttribute('value');
            var url = window.TIKI_PROTOCOL + '://' + location.host + '/tikibar/?correlation_id=' + correlation_id + '&render=1&run_js=1';
            return url;
        };

        TikibarHost.prototype.on_ajax_request = function(event, xhr, settings) {
            this.send_message({
                'tiki_msg_type': 'ajax_request',
                'url': settings.url,
                'verb': settings.type, // GET or POST
                'status_code': xhr.status,
                'ms': xhr.getResponseHeader('X-Tiki-Time') * 1000,
                'correlation_id': xhr.getResponseHeader('X-Correlation-ID')
            });
        }

        window.tikibar_host = TikibarHost({attach: document.body});

    });
}
