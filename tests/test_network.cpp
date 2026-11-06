#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
constexpr int INPUT=0, WIFI_AP=2;
static std::vector<std::string> calls;
static bool pinsOk=true,modeOk=true,addressOk=true,apOk=true;
void pinMode(int pin,int mode){assert(pin==6&&mode==INPUT);calls.push_back("boot-input");}
bool hostedSetPins(int c,int m,int d0,int d1,int d2,int d3,int reset){
 assert(c==18&&m==19&&d0==14&&d1==15&&d2==16&&d3==17&&reset==54);
 calls.push_back("pins");return pinsOk;
}
void hostedGetHostVersion(uint32_t*a,uint32_t*b,uint32_t*c){*a=2;*b=6;*c=1;calls.push_back("host-version");}
void hostedGetSlaveVersion(uint32_t*a,uint32_t*b,uint32_t*c){*a=2;*b=6;*c=0;calls.push_back("c6-version");}
struct IPAddress {
 uint8_t a,b,c,d;
 IPAddress(uint8_t a,uint8_t b,uint8_t c,uint8_t d):a(a),b(b),c(c),d(d){}
};
struct FakeWiFi {
 bool mode(int mode){assert(mode==WIFI_AP);calls.push_back("mode");return modeOk;}
 bool softAPConfig(IPAddress ip,IPAddress gateway,IPAddress mask){
  assert(ip.a==192&&ip.b==168&&ip.c==4&&ip.d==1);
  assert(gateway.a==192&&gateway.b==168&&gateway.c==4&&gateway.d==1);
  assert(mask.a==255&&mask.b==255&&mask.c==255&&mask.d==0);
  calls.push_back("address");return addressOk;
 }
 bool softAP(const char *ssid,const char *password){
  assert(!strcmp(ssid,"saved-network")&&!strcmp(password,"saved-password"));
  calls.push_back("ap");return apOk;
 }
} WiFi;
#include "p4_network.h"
static void reset(){
 calls.clear();pinsOk=modeOk=addressOk=apOk=true;
 p4NetworkPinsReady=p4NetworkWifiStarted=p4NetworkApStarted=false;
 p4NetworkPhase=P4_NET_NOT_STARTED;
}
int main(){
 reset();assert(!p4NetworkAllowsBle());assert(p4NetworkPrepare());
 assert(p4NetworkStartAp("saved-network","saved-password"));
 const std::vector<std::string> sequence={"boot-input","pins","mode","host-version","c6-version","address","ap"};
 assert(calls==sequence&&p4NetworkAllowsBle());assert(!strcmp(p4NetworkPhaseName(),"READY"));
 calls.clear();assert(p4NetworkStartAp("saved-network","saved-password"));
 assert(calls==std::vector<std::string>({"address","ap"})); // No Hosted restart on settings changes.
 reset();pinsOk=false;assert(!p4NetworkPrepare());assert(!p4NetworkStartAp("saved-network","saved-password"));
 assert(calls.size()==2&&!p4NetworkAllowsBle());assert(p4NetworkPhase==P4_NET_PINS_FAILED);
 reset();assert(p4NetworkPrepare());modeOk=false;assert(!p4NetworkStartAp("saved-network","saved-password"));
 assert(calls.back()=="mode"&&!p4NetworkAllowsBle());assert(p4NetworkPhase==P4_NET_WIFI_FAILED);
 modeOk=true;addressOk=false;assert(!p4NetworkStartAp("saved-network","saved-password"));
 assert(calls.back()=="address"&&!p4NetworkAllowsBle());assert(p4NetworkPhase==P4_NET_ADDRESS_FAILED);
 addressOk=true;apOk=false;assert(!p4NetworkStartAp("saved-network","saved-password"));
 assert(p4NetworkPhase==P4_NET_AP_FAILED&&!p4NetworkAllowsBle());
 apOk=true;assert(p4NetworkStartAp("saved-network","saved-password")&&p4NetworkAllowsBle());
 puts("PASS: reference Hosted sequence, GPIO6 input, fixed IP, all failure stages, retries, preserved credentials and BLE admission");
}
